"""Abrir aplicaciones instaladas (Steam, Epic Games, Visual Studio, Brave) y sus iconos.

La config de fábrica no trae estos botones (son ejemplos genéricos de Windows), así que los
tests que los necesitan los añaden con ``app_buttons``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from celldeck.apps import APPS
from celldeck.config.store import ConfigError, ConfigStore, default_config_data
from celldeck.platform.base import AppLocation
from celldeck.platform.fake import FakeBackend
from celldeck.plugins import PluginRegistry
from celldeck.plugins.runner import ActionRunner
from celldeck.state import AppState
from tests.conftest import auth, local_token

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
STEAM = AppLocation(path=r"D:\APPS\Steam\steam.exe", uri="steam://open/main", source="registro")


# ------------------------------------------------------------------ catálogo
def test_catalog_has_requested_apps() -> None:
    assert {"steam", "epic", "visualstudio", "brave"} <= set(APPS)
    assert APPS["epic"].scheme == "com.epicgames.launcher"
    assert APPS["visualstudio"].vswhere


APP_BUTTONS = {
    "steam": "steam",
    "epic-games": "epic",
    "visual-studio": "visualstudio",
    "brave": "brave",
}


def test_default_config_is_generic(registry: PluginRegistry) -> None:
    """La config de fábrica solo usa acciones que existen en cualquier Windows."""
    config = ConfigStore(Path("x.json"), registry).parse(default_config_data())
    actions = [i.action for p in config.pages for i in p.items if getattr(i, "action", None)]
    assert not [a for a in actions if a.type == "app"]
    pc = config.find_page("pc")
    assert pc is not None and {"calculator", "settings"} <= {i.id for i in pc.items}


@pytest.fixture
def app_buttons(state: AppState) -> None:
    """Añade a la página PC un botón por app del catálogo, con el logotipo oficial."""
    data = state.config_store.config.to_json_dict()
    pc = next(p for p in data["pages"] if p["id"] == "pc")
    pc["items"] += [
        {
            "kind": "button",
            "id": item,
            "label": APPS[app].name,
            "icon": "app",
            "action": {"type": "app", "app": app},
        }
        for item, app in APP_BUTTONS.items()
    ]
    state.config_store.save(state.config_store.parse(data))


def test_unknown_app_rejected(registry: PluginRegistry) -> None:
    data = {
        "pages": [
            {
                "id": "p",
                "name": "P",
                "items": [
                    {"kind": "button", "id": "b", "action": {"type": "app", "app": "photoshop"}}
                ],
            }
        ]
    }
    with pytest.raises(ConfigError, match="Aplicación desconocida"):
        ConfigStore(Path("x.json"), registry).parse(data)


# -------------------------------------------------------------------- plugin
def app_action(registry: PluginRegistry, app_id: str) -> Any:
    return registry.validate({"type": "app", "app": app_id})


async def test_opens_found_executable(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    backend.apps["steam"] = STEAM
    assert (await runner.run(app_action(registry, "steam"))).ok
    assert backend.calls == [("open_path", (STEAM.path, (), None))]


async def test_uses_protocol_when_only_uri_is_registered(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    backend.apps["epic"] = AppLocation(None, "com.epicgames.launcher://store", "protocolo")
    assert (await runner.run(app_action(registry, "epic"))).ok
    assert backend.calls == [("open_uri", ("com.epicgames.launcher://store",))]


async def test_not_installed(registry: PluginRegistry, runner: ActionRunner) -> None:
    result = await runner.run(app_action(registry, "visualstudio"))
    assert not result.ok and "No se encontró Visual Studio" in result.message


async def test_stale_path_is_searched_again(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    """Si la ruta cacheada ya no sirve, se olvida y se busca de nuevo."""
    backend.apps["brave"] = AppLocation(r"C:\viejo\brave.exe", None, "App Paths")
    backend.fail_with = "No se encontró el archivo"  # la primera apertura falla
    result = await runner.run(app_action(registry, "brave"))
    assert not result.ok  # sigue en la misma ruta inexistente → error claro
    assert ("forget_app", ("brave",)) in backend.calls


# ----------------------------------------------------------------------- API
def test_apps_endpoint(client: TestClient, backend: FakeBackend) -> None:
    backend.apps["steam"] = STEAM
    data = client.get("/api/apps", headers=auth(local_token(client))).json()["apps"]
    by_id = {a["id"]: a for a in data}
    assert by_id["steam"]["installed"] is True and by_id["steam"]["source"] == "registro"
    assert by_id["epic"]["installed"] is False
    assert by_id["brave"]["fallback_icon"] == "globe"


@pytest.mark.usefixtures("app_buttons")
def test_icon_endpoint(client: TestClient, backend: FakeBackend) -> None:
    token = local_token(client)
    backend.apps["steam"] = STEAM
    backend.icons[STEAM.path] = PNG  # type: ignore[index]
    res = client.get(f"/api/icon/pc/steam?v=1&token={token}")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert res.content == PNG and "max-age" in res.headers["cache-control"]
    # App no instalada → 404 (el celular muestra el icono genérico)
    assert client.get(f"/api/icon/pc/epic-games?token={token}").status_code == 404
    # Solo botones de la config: nada de rutas arbitrarias
    assert client.get(f"/api/icon/pc/no-existe?token={token}").status_code == 404
    assert client.get("/api/icon/pc/steam").status_code == 401


def test_icon_for_launch_and_url_buttons(client: TestClient, backend: FakeBackend) -> None:
    token = local_token(client)
    backend.icons["explorer.exe"] = PNG
    backend.icons["https://github.com"] = PNG
    assert client.get(f"/api/icon/pc/explorer?token={token}").status_code == 200
    assert client.get(f"/api/icon/pc/github?token={token}").status_code == 200


@pytest.mark.usefixtures("app_buttons")
def test_run_app_button(client: TestClient, backend: FakeBackend, state: AppState) -> None:
    backend.apps["visualstudio"] = AppLocation(r"C:\VS\devenv.exe", None, "vswhere")
    res = client.post(
        "/api/run", json={"page": "pc", "item": "visual-studio"}, headers=auth(local_token(client))
    )
    assert res.json()["ok"] is True
    assert backend.calls == [("open_path", (r"C:\VS\devenv.exe", (), None))]


# ---------------------------------------------------------- Windows (registro)
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")


@win_only
def test_parse_registry_paths(tmp_path: Path) -> None:
    from celldeck.platform.windows_apps import clean_path, exe_from_command

    exe = tmp_path / "Steam" / "steam.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert exe_from_command(f'"{exe}" -- "%1"') == str(exe)
    assert exe_from_command(f"{exe} %1") == str(exe)
    assert clean_path(f'"{exe}"') == str(exe)
    assert clean_path(f"{exe},0") == str(exe)  # DisplayIcon con índice
    assert clean_path(str(tmp_path / "no-existe.exe")) is None
    assert exe_from_command(None) is None


@win_only
def test_extract_real_icon_from_explorer() -> None:
    from celldeck.platform.windows_apps import extract_icon_png, resolve_target

    exe = resolve_target("explorer.exe")
    assert exe is not None and exe.lower().endswith("explorer.exe")
    png = extract_icon_png(exe, 64)
    assert png is not None and png.startswith(b"\x89PNG")


@win_only
async def test_windows_backend_find_app_is_cached() -> None:
    from celldeck.platform.windows import WindowsBackend

    backend = WindowsBackend()
    try:
        first = await backend.find_app("brave")
        second = await backend.find_app("brave")
        assert first == second  # mismo resultado (desde caché), instalada o no
        assert await backend.find_app("no-existe") is None
    finally:
        await backend.close()
