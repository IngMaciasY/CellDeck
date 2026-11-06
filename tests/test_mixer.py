"""Volume Mixer: agrupado de sesiones, comandos, sincronización e iconos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from phonedeck.platform.audio import SYSTEM_KEY, SessionRow, app_key, group_sessions
from phonedeck.platform.base import AudioApp, PlatformError
from phonedeck.platform.fake import FakeBackend
from phonedeck.services.mixer import MixerService, mixer_payload
from phonedeck.state import AppState
from tests.conftest import auth, local_token
from tests.test_live import WS_URL, receive_until
from tests.test_services import spy_broadcasts

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
BRAVE = r"C:\Apps\Brave\brave.exe"


def apps(backend: FakeBackend) -> None:
    backend.audio_apps = {
        "brave": AudioApp("brave", "Brave", 40, False, BRAVE),
        "steam": AudioApp("steam", "Steam", 90, False),
    }


def row(key: str, volume: float, muted: bool = False, name: str = "App") -> SessionRow:
    return SessionRow(key, name, None, volume, muted)


def test_sessions_of_one_app_are_grouped() -> None:
    result = group_sessions([row("a", 0.3, muted=True), row("a", 0.8), row("a", 0.5, muted=True)])
    assert [(a.key, a.level, a.muted) for a in result] == [("a", 80, False)]


def test_app_counts_as_muted_only_if_every_session_is() -> None:
    assert group_sessions([row("a", 0.5, True), row("a", 0.5, True)])[0].muted is True
    assert group_sessions([row("a", 0.5, True), row("a", 0.5, False)])[0].muted is False


def test_order_is_alphabetical_with_system_last() -> None:
    rows = [
        row(SYSTEM_KEY, 1, name="Sonidos del sistema"),
        row("z", 1, name="zoom"),
        row("b", 1, name="Brave"),
    ]
    assert [a.name for a in group_sessions(rows)] == ["Brave", "zoom", "Sonidos del sistema"]


def test_app_key_is_opaque_and_ignores_case() -> None:
    key = app_key(BRAVE)
    assert key == app_key(BRAVE.upper())
    assert "brave" not in key and len(key) == 16


def test_payload_never_includes_the_path() -> None:
    payload = mixer_payload([AudioApp("brave", "Brave", 40, False, BRAVE)])
    assert payload == {
        "apps": [{"key": "brave", "name": "Brave", "level": 40, "muted": False, "icon": True}],
        "error": None,
    }
    assert BRAVE not in str(payload)


async def test_service_broadcasts_only_changes(state: AppState, backend: FakeBackend) -> None:
    apps(backend)
    sent = spy_broadcasts(state)
    service = MixerService(state)
    await service.tick()
    await service.tick()
    assert len(sent) == 1
    assert state.live.audio_paths == {"brave": BRAVE}

    await backend.set_app_volume("brave", 10)  # cambio hecho desde la PC
    await service.tick()
    assert sent[-1][1]["apps"][0]["level"] == 10


async def test_service_reports_audio_failure(state: AppState, backend: FakeBackend) -> None:
    apps(backend)

    async def broken() -> list[AudioApp]:
        raise PlatformError("No se pudo leer el audio de Windows")

    backend.list_audio_apps = broken  # type: ignore[method-assign]
    sent = spy_broadcasts(state)
    await MixerService(state).tick()
    assert sent[0][1] == {"apps": [], "error": "No se pudo leer el audio de Windows"}


def test_changes_one_app_without_touching_the_others(
    client: TestClient, backend: FakeBackend
) -> None:
    apps(backend)
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "mixer.set", "key": "brave", "value": 15})
        ws.send_json({"type": "mixer.mute", "key": "brave", "muted": True})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
    assert backend.audio_apps["brave"].level == 15
    assert backend.audio_apps["brave"].muted is True
    assert backend.audio_apps["steam"] == AudioApp("steam", "Steam", 90, False)


def test_invalid_mixer_commands(client: TestClient, backend: FakeBackend) -> None:
    apps(backend)
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "mixer.set", "key": "brave", "value": 101})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "mixer.set", "key": r"C:\Windows\x.exe", "value": 10})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "mixer.mute", "key": "cerrada", "muted": True})
        assert receive_until(ws, "error")["data"]["message"] == "Esa aplicación ya no tiene audio"
    assert backend.audio_apps["brave"].level == 40


def test_mixer_requires_its_widget(client: TestClient, backend: FakeBackend) -> None:
    apps(backend)
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    for page in current["config"]["pages"]:
        page["items"] = [i for i in page["items"] if i.get("widget") != "mixer"]
    assert client.put("/api/config", json=current, headers=h).status_code == 200

    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "mixer.set", "key": "brave", "value": 10})
        assert "no hay widget 'mixer'" in receive_until(ws, "error")["data"]["message"]
    assert backend.audio_apps["brave"].level == 40


def test_mixer_icon_only_for_live_apps(
    client: TestClient, state: AppState, backend: FakeBackend
) -> None:
    token = local_token(client)
    backend.icons[BRAVE] = PNG
    assert client.get("/api/mixer/icon/brave").status_code == 401
    assert client.get(f"/api/mixer/icon/brave?token={token}").status_code == 404

    state.live.audio_paths = {"brave": BRAVE}
    res = client.get(f"/api/mixer/icon/brave?token={token}")
    assert res.status_code == 200
    assert res.content == PNG
    assert client.get(f"/api/mixer/icon/otra?token={token}").status_code == 404
