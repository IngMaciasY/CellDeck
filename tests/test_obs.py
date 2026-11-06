"""Puente con OBS: autenticación, escenas, eventos, reconexión y permisos."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from phonedeck import obs as obs_module
from phonedeck.config.settings import Settings
from phonedeck.obs import ObsBridge, ObsError, auth_response, scene_names
from phonedeck.server import create_app
from phonedeck.state import AppState
from phonedeck.ws import WebSocketHub
from tests.conftest import LAN_HOST, auth, local_token
from tests.fake_obs import FakeObs
from tests.test_live import WS_URL, receive_until

SCENES = ["Juego", "Cámara", "Pausa"]


class Viewer:
    """Un celular mirando la sección de OBS."""

    async def send_text(self, _text: str) -> None:
        return None


class Harness:
    def __init__(self, port: int, password: str = "") -> None:
        self.settings = Settings(obs_port=port, obs_password=password)
        self.hub = WebSocketHub()
        self.hub._clients[Viewer()] = frozenset({"obs"})  # type: ignore[index]
        self.bridge = ObsBridge(self.hub, lambda: self.settings)

    async def until(self, check: Callable[[dict[str, Any]], bool], limit: float = 3.0) -> None:
        async with asyncio.timeout(limit):
            while not check(self.bridge.payload()):  # noqa: ASYNC110
                await asyncio.sleep(0.01)

    async def online(self) -> None:
        await self.until(lambda p: p["status"] == "online")


@contextlib.asynccontextmanager
async def running(harness: Harness) -> AsyncIterator[Harness]:
    task = asyncio.create_task(harness.bridge.run())
    try:
        yield harness
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs_module, "MIN_RETRY_S", 0.02)
    monkeypatch.setattr(obs_module, "MAX_RETRY_S", 0.05)
    monkeypatch.setattr(obs_module, "READ_CHECK_S", 0.02)


@pytest.fixture
async def server() -> AsyncIterator[FakeObs]:
    fake = FakeObs(list(SCENES))
    await fake.start()
    yield fake
    await fake.stop()


def test_auth_matches_the_documented_algorithm() -> None:
    secret = base64.b64encode(hashlib.sha256(b"clave" + b"sal").digest()).decode()
    final = hashlib.sha256((secret + "reto").encode()).digest()
    assert auth_response("clave", "sal", "reto") == base64.b64encode(final).decode()


def test_scene_order_follows_the_obs_list() -> None:
    scenes = [
        {"sceneIndex": 0, "sceneName": "Abajo"},
        {"sceneIndex": 2, "sceneName": "Arriba"},
        {"sceneIndex": 1, "sceneName": "Medio"},
    ]
    assert scene_names(scenes) == ["Arriba", "Medio", "Abajo"]


async def test_reads_scenes_and_subscribes_to_events(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        data = h.bridge.payload()
    assert data["scenes"] == SCENES
    assert data["current"] == "Juego"
    assert server.subscriptions == (1 << 1) | (1 << 2)


async def test_authenticates_with_password() -> None:
    fake = FakeObs(list(SCENES), password="secreta")
    await fake.start()
    try:
        async with running(Harness(fake.port, "secreta")) as h:
            await h.online()
    finally:
        await fake.stop()


@pytest.mark.parametrize(
    "password,message",
    [("mala", obs_module.AUTH_REJECTED_MESSAGE), ("", obs_module.AUTH_MISSING_MESSAGE)],
)
async def test_reports_auth_failure(password: str, message: str) -> None:
    fake = FakeObs(list(SCENES), password="secreta")
    await fake.start()
    try:
        async with running(Harness(fake.port, password)) as h:
            await h.until(lambda p: p["status"] == "auth_failed")
            assert h.bridge.payload()["message"] == message
    finally:
        await fake.stop()


async def test_changes_scene_and_follows_changes_made_in_obs(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        await h.bridge.set_scene("Cámara")
        await h.until(lambda p: p["current"] == "Cámara")
        assert server.current == "Cámara"

        await server.switch("Pausa")  # alguien cambia de escena en la propia OBS
        await h.until(lambda p: p["current"] == "Pausa")


async def test_scene_list_refreshes_on_obs_events(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        server.scenes.append("Nueva")
        await server.emit("SceneListChanged", {"scenes": []})
        await h.until(lambda p: "Nueva" in p["scenes"])


async def test_rejects_scenes_outside_the_list(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        with pytest.raises(ObsError, match="ya no existe"):
            await h.bridge.set_scene("Inventada")
    assert "SetCurrentProgramScene" not in server.requests


async def test_reports_failure_from_obs(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        server.scenes.remove("Pausa")  # OBS la borró y el evento aún no llegó
        with pytest.raises(ObsError, match="no pudo cambiar"):
            await h.bridge.set_scene("Pausa")


async def test_scene_change_fails_cleanly_when_offline() -> None:
    bridge = ObsBridge(WebSocketHub(), Settings)
    with pytest.raises(ObsError, match="no está conectado"):
        await bridge.set_scene("Juego")


async def test_offline_when_obs_is_closed() -> None:
    fake = FakeObs(list(SCENES))
    await fake.start()
    port = fake.port
    await fake.stop()
    async with running(Harness(port)) as h:
        await h.until(lambda p: p["status"] == "offline")
        assert h.bridge.payload()["scenes"] == []


async def test_recovers_when_obs_restarts(server: FakeObs) -> None:
    async with running(Harness(server.port)) as h:
        await h.online()
        await server.stop()
        await h.until(lambda p: p["status"] == "offline")
        await server.start()
        await h.online()
        assert h.bridge.payload()["scenes"] == SCENES


async def test_no_connection_without_viewers(server: FakeObs) -> None:
    h = Harness(server.port)
    h.hub._clients.clear()
    async with running(h):
        await asyncio.sleep(0.1)
    assert server.requests == []


async def test_closes_after_nobody_is_watching(
    server: FakeObs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(obs_module, "IDLE_CLOSE_S", 0.05)
    async with running(Harness(server.port)) as h:
        await h.online()
        h.hub._clients.clear()
        await h.until(lambda p: p["status"] == "connecting")
        await asyncio.sleep(0.05)
        assert not server.clients


async def test_new_password_applies_at_once() -> None:
    fake = FakeObs(list(SCENES), password="secreta")
    await fake.start()
    try:
        async with running(Harness(fake.port, "mala")) as h:
            await h.until(lambda p: p["status"] == "auth_failed")
            h.settings = Settings(obs_port=fake.port, obs_password="secreta")
            await h.bridge.reconnect()
            await h.online()
    finally:
        await fake.stop()


# ------------------------------------------------------------- ajustes y comandos
def test_settings_never_return_the_password(client: TestClient, state: AppState) -> None:
    h = auth(local_token(client))
    assert client.get("/api/obs/settings").status_code == 401
    assert client.get("/api/obs/settings", headers=h).json() == {
        "host": "127.0.0.1",
        "port": 4455,
        "has_password": False,
    }
    body = {"host": "127.0.0.1", "port": 4460, "password": "secreta"}
    saved = client.put("/api/obs/settings", json=body, headers=h)
    assert saved.status_code == 200
    assert "secreta" not in saved.text
    assert saved.json()["has_password"] is True
    assert state.settings.obs_password == "secreta"

    kept = client.put("/api/obs/settings", json={"host": "localhost", "port": 4460}, headers=h)
    assert kept.json()["host"] == "localhost"
    assert state.settings.obs_password == "secreta"  # sin campo: se conserva


@pytest.mark.parametrize(
    "body",
    [
        {"host": "evil.com/x", "port": 4455},
        {"host": "a b", "port": 4455},
        {"host": "127.0.0.1", "port": 0},
        {"host": "127.0.0.1", "port": 70000},
    ],
)
def test_settings_validate_host_and_port(client: TestClient, body: dict[str, Any]) -> None:
    res = client.put("/api/obs/settings", json=body, headers=auth(local_token(client)))
    assert res.status_code == 422


def test_settings_are_rejected_from_the_network(tmp_path: Path, state: AppState) -> None:
    state.settings_store.update(extra_allowed_hosts=[LAN_HOST], allow_remote_edit=True)
    state.allowed_hosts.extra = [LAN_HOST]
    token = state.tokens.issue("celular", 1)
    h = auth(token)
    url = f"http://{LAN_HOST}:8765"
    with TestClient(create_app(state), base_url=url, client=("192.168.1.50", 1)) as lan:
        assert lan.get("/api/obs/settings", headers=h).status_code == 403
        body = {"host": "10.0.0.5", "port": 4455, "password": "x"}
        assert lan.put("/api/obs/settings", json=body, headers=h).status_code == 403
    assert state.settings.obs_password == ""


def test_scene_command_reports_obs_offline(client: TestClient) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "obs.scene", "name": "Juego"})
        assert receive_until(ws, "error")["data"]["message"] == "OBS no está conectado"


def test_scene_command_validates_input(client: TestClient) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "obs.scene", "name": ""})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "obs.scene", "name": 5})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"


def test_scene_command_requires_its_widget(client: TestClient) -> None:
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    for page in current["config"]["pages"]:
        page["items"] = [i for i in page["items"] if i.get("widget") != "obs"]
    assert client.put("/api/config", json=current, headers=h).status_code == 200

    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "obs.scene", "name": "Juego"})
        assert "no hay widget 'obs'" in receive_until(ws, "error")["data"]["message"]
