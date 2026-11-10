"""API HTTP y WebSocket de punta a punta (con FakeBackend)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from celldeck.platform.fake import FakeBackend
from celldeck.server import create_app
from celldeck.state import AppState
from tests.conftest import LAN_HOST, auth, local_token, make_state

# El TestClient usa Host 'testserver' en WebSocket salvo que se pase la URL completa.
WS_URL = "ws://127.0.0.1:8765/ws"


@pytest.fixture
def wifi_state(tmp_path: Path, backend: FakeBackend) -> AppState:
    return make_state(tmp_path, backend, mode="wifi")


@pytest.fixture
def remote(wifi_state: AppState) -> Iterator[TestClient]:
    """Celular por WiFi: IP de la LAN, Host = IP de la PC."""
    app = create_app(wifi_state)
    with TestClient(app, base_url=f"http://{LAN_HOST}:8765", client=("192.168.1.50", 40000)) as c:
        yield c


# ------------------------------------------------------------------- USB/local
def test_health_and_security_headers(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200 and res.json()["ok"] is True
    assert res.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in res.headers["content-security-policy"]


def test_host_header_rejected(state: AppState) -> None:
    app = create_app(state)
    with TestClient(app, base_url="http://evil.example:8765", client=("127.0.0.1", 1)) as c:
        assert c.get("/api/health").status_code == 421


def test_local_session_gives_token(client: TestClient) -> None:
    data = client.get("/api/session").json()
    assert data["loopback"] is True and data["can_edit"] is True and data["token"]


def test_run_requires_token(client: TestClient, backend: FakeBackend) -> None:
    res = client.post("/api/run", json={"page": "media", "item": "play-pause"})
    assert res.status_code == 401
    assert backend.calls == []


def test_run_button(client: TestClient, backend: FakeBackend) -> None:
    token = local_token(client)
    res = client.post("/api/run", json={"page": "media", "item": "play-pause"}, headers=auth(token))
    assert res.status_code == 200 and res.json()["ok"] is True
    assert backend.names() == ["send_media_key"]


def test_run_unknown_or_widget(client: TestClient) -> None:
    h = auth(local_token(client))
    assert (
        client.post("/api/run", json={"page": "media", "item": "nope"}, headers=h).status_code
        == 404
    )
    assert (
        client.post(
            "/api/run", json={"page": "media", "item": "now-playing"}, headers=h
        ).status_code
        == 404
    )


def test_confirm_required(client: TestClient, backend: FakeBackend) -> None:
    h = auth(local_token(client))
    res = client.post("/api/run", json={"page": "pc", "item": "sleep"}, headers=h)
    assert res.status_code == 428 and res.json()["detail"]["confirm_required"] is True
    assert backend.calls == []
    res = client.post(
        "/api/run", json={"page": "pc", "item": "sleep", "confirmed": True}, headers=h
    )
    assert res.status_code == 200 and backend.names() == ["system_command"]


def test_cannot_send_arbitrary_actions(client: TestClient, backend: FakeBackend) -> None:
    """El endpoint ignora cualquier 'action' enviada: solo vale lo que está en la config."""
    h = auth(local_token(client))
    body = {"page": "media", "item": "next", "action": {"type": "launch", "path": "cmd.exe"}}
    res = client.post("/api/run", json=body, headers=h)
    assert res.status_code == 200
    assert backend.names() == ["send_media_key"]


def test_get_and_put_config(client: TestClient, state: AppState) -> None:
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    config = current["config"]
    config["pages"][0]["name"] = "Música"
    res = client.put(
        "/api/config", json={"revision": current["revision"], "config": config}, headers=h
    )
    assert res.status_code == 200
    assert state.config_store.config.pages[0].name == "Música"

    # Revisión vieja → conflicto
    res = client.put(
        "/api/config", json={"revision": current["revision"], "config": config}, headers=h
    )
    assert res.status_code == 409

    # Config inválida → 422 con detalle
    config["pages"][0]["items"][1]["action"] = {"type": "keys", "combo": "ctrl+xyz"}
    res = client.put("/api/config", json={"config": config}, headers=h)
    assert res.status_code == 422
    assert "Tecla desconocida" in res.json()["detail"]["message"]


def test_plugins_endpoint(client: TestClient) -> None:
    data = client.get("/api/plugins", headers=auth(local_token(client))).json()
    assert {p["type"] for p in data["plugins"]} >= {"media", "macro"}
    assert "ctrl" in data["keys"]


def test_websocket_requires_token_and_receives_config(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(WS_URL) as ws:
        ws.receive_text()

    token = local_token(client)
    with client.websocket_connect(f"{WS_URL}?token={token}") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        h = auth(token)
        current = client.get("/api/config", headers=h).json()
        current["config"]["pages"][0]["name"] = "Por WS"
        client.put("/api/config", json=current, headers=h)
        msg = ws.receive_json()
        assert msg["type"] == "config"
        assert msg["data"]["config"]["pages"][0]["name"] == "Por WS"


# ----------------------------------------------------------------------- WiFi
def test_remote_session_requires_pairing(remote: TestClient) -> None:
    assert remote.get("/api/session").status_code == 401


def test_remote_pairing_flow(
    remote: TestClient, wifi_state: AppState, backend: FakeBackend
) -> None:
    assert (
        remote.post(
            "/api/pair", json={"pin": "000000" if wifi_state.settings.pin != "000000" else "111111"}
        ).status_code
        == 403
    )
    res = remote.post("/api/pair", json={"pin": wifi_state.settings.pin, "device": "Redmi"})
    assert res.status_code == 200
    data = res.json()
    assert data["loopback"] is False and data["can_edit"] is False
    h = auth(data["token"])
    assert remote.get("/api/session", headers=h).status_code == 200
    assert remote.post("/api/run", json={"page": "media", "item": "next"}, headers=h).json()["ok"]
    assert backend.names() == ["send_media_key"]


def test_remote_cannot_edit_by_default(remote: TestClient, wifi_state: AppState) -> None:
    token = remote.post("/api/pair", json={"pin": wifi_state.settings.pin}).json()["token"]
    current = remote.get("/api/config", headers=auth(token)).json()
    res = remote.put("/api/config", json=current, headers=auth(token))
    assert res.status_code == 403

    wifi_state.settings_store.update(allow_remote_edit=True)
    current = remote.get("/api/config", headers=auth(token)).json()
    assert remote.put("/api/config", json=current, headers=auth(token)).status_code == 200


def test_pin_bruteforce_locks(remote: TestClient, wifi_state: AppState) -> None:
    wrong = "000000" if wifi_state.settings.pin != "000000" else "111111"
    codes = [remote.post("/api/pair", json={"pin": wrong}).status_code for _ in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    # Ni siquiera el PIN correcto funciona durante el bloqueo
    assert remote.post("/api/pair", json={"pin": wifi_state.settings.pin}).status_code == 429


def test_revoke_devices(remote: TestClient, wifi_state: AppState) -> None:
    token = remote.post("/api/pair", json={"pin": wifi_state.settings.pin}).json()["token"]
    wifi_state.settings_store.revoke_all_devices()
    assert remote.get("/api/config", headers=auth(token)).status_code == 401


def test_validate_config_endpoint(client: TestClient, state: AppState) -> None:
    h = auth(local_token(client))
    config = client.get("/api/config", headers=h).json()["config"]
    assert client.post("/api/config/validate", json={"config": config}, headers=h).json() == {
        "ok": True
    }
    config["pages"][0]["items"][1]["action"] = {"type": "keys", "combo": "ctrl+nope"}
    res = client.post("/api/config/validate", json={"config": config}, headers=h)
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["loc"].startswith("pages.0.items.1")
    assert not res.json()["detail"]["errors"][0]["msg"].startswith("Value error")
    # Validar no guarda nada
    assert state.config_store.config.pages[0].items[1].action.type == "media"


def test_remote_cannot_validate_without_edit_permission(
    remote: TestClient, wifi_state: AppState
) -> None:
    token = remote.post("/api/pair", json={"pin": wifi_state.settings.pin}).json()["token"]
    config = remote.get("/api/config", headers=auth(token)).json()["config"]
    res = remote.post("/api/config/validate", json={"config": config}, headers=auth(token))
    assert res.status_code == 403
