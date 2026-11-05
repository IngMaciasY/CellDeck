"""Comandos en vivo por WebSocket y portada."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from phonedeck.platform.base import MediaKey
from phonedeck.platform.fake import FakeBackend
from phonedeck.state import AppState, Artwork
from tests.conftest import auth, local_token

WS_URL = "ws://127.0.0.1:8765/ws"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def receive_until(ws: Any, msg_type: str, limit: int = 10) -> dict[str, Any]:
    for _ in range(limit):
        msg: dict[str, Any] = ws.receive_json()
        if msg["type"] == msg_type:
            return msg
    raise AssertionError(f"No llegó un mensaje '{msg_type}'")


def test_volume_set_and_mute(client: TestClient, backend: FakeBackend) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "volume.set", "value": 30})
        assert receive_until(ws, "volume")["data"] == {"level": 30, "muted": False}
        ws.send_json({"type": "volume.mute", "muted": True})
        assert receive_until(ws, "volume")["data"] == {"level": 30, "muted": True}
    assert backend.calls == [("set_volume", (30,)), ("set_mute", (True,))]


def test_invalid_live_commands(client: TestClient, backend: FakeBackend) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "volume.set", "value": 150})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "media", "command": "format_c"})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "launch", "path": "cmd.exe"})  # tipo desconocido: se ignora
        ws.send_json({"type": "ping"})
        assert receive_until(ws, "pong")
    assert backend.calls == []


def test_media_command(client: TestClient, backend: FakeBackend) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "media", "command": "next"})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
    assert backend.calls == [("send_media_key", (MediaKey.NEXT,))]


def test_live_command_requires_widget_in_config(
    client: TestClient, state: AppState, backend: FakeBackend
) -> None:
    """Sin widget de volumen en la config, el celular no puede usar ese control."""
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    for page in current["config"]["pages"]:
        page["items"] = [
            i for i in page["items"] if i.get("widget") not in ("volume", "now_playing")
        ]
    assert client.put("/api/config", json=current, headers=h).status_code == 200

    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "volume.set", "value": 10})
        assert "no hay widget 'volume'" in receive_until(ws, "error")["data"]["message"]
        ws.send_json({"type": "media", "command": "play_pause"})
        assert "now_playing" in receive_until(ws, "error")["data"]["message"]
    assert backend.calls == []


def test_artwork_endpoint(client: TestClient, state: AppState) -> None:
    token = local_token(client)
    assert client.get("/api/media/artwork").status_code == 401
    assert client.get(f"/api/media/artwork?token={token}").status_code == 404

    state.live.artwork = Artwork("abc123", PNG, "image/png")
    res = client.get(f"/api/media/artwork?h=abc123&token={token}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == PNG
    assert "max-age" in res.headers["cache-control"]  # la API no impone no-store aquí
    assert client.get(f"/api/media/artwork?h=otro&token={token}").status_code == 404
