"""Piezas de escritorio: adb, emparejamiento, controlador del servidor y bandeja."""

from __future__ import annotations

import socket
import subprocess
import urllib.request
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from phonedeck import adb, winui
from phonedeck.app import LaunchOptions, PortInUseError, ServerController
from phonedeck.platform.fake import FakeBackend
from phonedeck.server import create_app
from phonedeck.state import AppState
from tests.conftest import LAN_HOST, auth, local_token, make_state


# ------------------------------------------------------------------------ adb
class FakeAdb:
    def __init__(self, devices: str, reverse_rc: int = 0) -> None:
        self.devices = devices
        self.reverse_rc = reverse_rc
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        args = list(args)
        self.calls.append(args)
        out, rc = "", 0
        if args[1:] == ["devices"]:
            out = self.devices
        elif "reverse" in args:
            rc = self.reverse_rc
        elif "getprop" in args:
            out = "Redmi 5 Plus\n"
        return subprocess.CompletedProcess(args, rc, out, "error de prueba" if rc else "")


@pytest.fixture
def fake_adb_path(tmp_path: Path) -> str:
    exe = tmp_path / "adb.exe"
    exe.write_text("", encoding="utf-8")
    return str(exe)


def test_parse_devices() -> None:
    out = "List of devices attached\n343304f6\tdevice\nabc\tunauthorized\n\n"
    assert adb.parse_devices(out) == [("343304f6", "device"), ("abc", "unauthorized")]


def test_connect_usb_ok(fake_adb_path: str) -> None:
    runner = FakeAdb("List of devices attached\n343304f6\tdevice\n")
    result = adb.connect_usb(8765, fake_adb_path, runner=runner)
    assert result.ok and result.devices == ["Redmi 5 Plus"]
    assert [fake_adb_path, "-s", "343304f6", "reverse", "tcp:8765", "tcp:8765"] in runner.calls
    opened = [c for c in runner.calls if "am" in c]
    assert opened and opened[0][-1] == "http://localhost:8765/"  # http:// explícito


@pytest.mark.parametrize(
    "devices,fragment",
    [
        ("List of devices attached\n", "No hay ningún celular"),
        ("List of devices attached\nabc\tunauthorized\n", "no autorizó"),
    ],
)
def test_connect_usb_errors(fake_adb_path: str, devices: str, fragment: str) -> None:
    result = adb.connect_usb(8765, fake_adb_path, runner=FakeAdb(devices))
    assert not result.ok and fragment in result.message


def test_connect_usb_reverse_fails(fake_adb_path: str) -> None:
    runner = FakeAdb("List of devices attached\nx\tdevice\n", reverse_rc=1)
    result = adb.connect_usb(8765, fake_adb_path, runner=runner)
    assert not result.ok and "adb reverse falló" in result.message


def test_connect_usb_without_adb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adb, "find_adb", lambda _p=None: None)
    result = adb.connect_usb(8765, runner=FakeAdb(""))
    assert not result.ok and "No se encontró adb" in result.message


# ------------------------------------------------------------- emparejamiento
def test_pairing_info_local(state: AppState, client: TestClient) -> None:
    data = client.get("/api/pairing", headers=auth(local_token(client))).json()
    assert data["mode"] == "usb" and data["pin"] == state.settings.pin
    assert data["urls"] == []  # en modo USB no hay URLs de WiFi
    assert client.get("/api/pairing").status_code == 401


@pytest.fixture
def wifi_local(tmp_path: Path, backend: FakeBackend) -> Iterator[tuple[TestClient, AppState]]:
    st = make_state(tmp_path, backend, mode="wifi")
    with TestClient(create_app(st), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1)) as c:
        yield c, st


def test_pairing_qr_only_for_pairing_urls(wifi_local: tuple[TestClient, AppState]) -> None:
    client, st = wifi_local
    h = auth(local_token(client))
    info = client.get("/api/pairing", headers=h).json()
    if not info["urls"]:
        pytest.skip("Sin red local en este equipo")
    assert info["urls"][0].endswith(f"#pin={st.settings.pin}")
    res = client.get("/api/pairing/qr.png", params={"url": info["urls"][0]}, headers=h)
    assert res.status_code == 200 and res.content.startswith(b"\x89PNG")
    bad = client.get("/api/pairing/qr.png", params={"url": "https://evil.example"}, headers=h)
    assert bad.status_code == 400


def test_pairing_forbidden_from_network(tmp_path: Path, backend: FakeBackend) -> None:
    """Un celular por WiFi nunca puede leer el PIN."""
    st = make_state(tmp_path, backend, mode="wifi")
    app = create_app(st)
    with TestClient(app, base_url=f"http://{LAN_HOST}:8765", client=("192.168.1.50", 1)) as c:
        token = c.post("/api/pair", json={"pin": st.settings.pin}).json()["token"]
        assert c.get("/api/pairing", headers=auth(token)).status_code == 403


# ------------------------------------------------------- controlador servidor
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def test_server_controller_start_stop(tmp_path: Path) -> None:
    port = free_port()
    ctl = ServerController(LaunchOptions(data_dir=tmp_path, fake=True, port=port))
    ctl.start()
    try:
        assert ctl.running and ctl.state is not None and ctl.state.loop is not None
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as res:
            assert res.status == 200
        # Una segunda instancia en el mismo puerto falla con un error claro
        with pytest.raises(PortInUseError):
            ServerController(LaunchOptions(data_dir=tmp_path, fake=True, port=port)).start()
        # Ejecutar corrutinas en el bucle del servidor desde otro hilo
        assert ctl.state.run_threadsafe(ctl.state.backend.get_volume()).level == 50
    finally:
        ctl.stop()
    assert not ctl.running


# --------------------------------------------------------------------- bandeja
class FakeController:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.running = True
        self.port = 8765
        self.options = LaunchOptions(data_dir=state.data_dir)

    def panel_url(self) -> str:
        return "http://127.0.0.1:8765/"


@pytest.fixture
def tray(state: AppState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from phonedeck.tray import TrayApp

    monkeypatch.setattr(winui, "ask", lambda *a, **k: True)  # el usuario responde "Sí"
    return TrayApp(FakeController(state), tmp_path, tmp_path / "phonedeck.log")  # type: ignore[arg-type]


def test_tray_tooltip(tray: Any) -> None:
    assert tray.tooltip().endswith("USB · 0 dispositivos")


def test_tray_settings_actions(tray: Any, state: AppState) -> None:
    old_pin = state.settings.pin
    tray.new_pin()
    assert state.settings.pin != old_pin

    assert state.settings.allow_remote_edit is False
    tray.toggle_remote_edit()
    assert state.settings.allow_remote_edit is True
    tray.toggle_remote_edit()
    assert state.settings.allow_remote_edit is False

    token = state.tokens.issue("redmi", 1)
    tray.revoke_all()
    assert state.tokens.verify(token) is None


def test_tray_remote_edit_declined(
    tray: Any, state: AppState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(winui, "ask", lambda *a, **k: False)
    tray.toggle_remote_edit()
    assert state.settings.allow_remote_edit is False


def test_tray_menu_builds(tray: Any) -> None:
    pytest.importorskip("pystray")
    menu = tray.build_menu()
    labels = [str(i.text) for i in menu.items if i.text]
    assert "Conectar celular por USB" in labels and "Salir" in labels
