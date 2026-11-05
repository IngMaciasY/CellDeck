"""Plugins con la capa Windows simulada (FakeBackend)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from phonedeck.platform.base import MediaKey, SystemCommand
from phonedeck.platform.fake import FakeBackend
from phonedeck.plugins import PluginRegistry
from phonedeck.plugins.loader import load_external_plugins
from phonedeck.plugins.runner import ActionRunner


def action(registry: PluginRegistry, data: dict[str, Any]) -> Any:
    return registry.validate(data)


async def test_media(registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend) -> None:
    result = await runner.run(action(registry, {"type": "media", "command": "play_pause"}))
    assert result.ok
    assert backend.calls == [("send_media_key", (MediaKey.PLAY_PAUSE,))]


@pytest.mark.parametrize(
    "op,value,expected_level,expected_muted",
    [
        ("set", 30, 30, False),
        ("step", 10, 60, False),
        ("step", -80, 0, False),
        ("step", 90, 100, False),
        ("toggle_mute", 0, 50, True),
        ("mute", 0, 50, True),
    ],
)
async def test_volume(
    registry: PluginRegistry,
    runner: ActionRunner,
    backend: FakeBackend,
    op: str,
    value: int,
    expected_level: int,
    expected_muted: bool,
) -> None:
    result = await runner.run(action(registry, {"type": "volume", "op": op, "value": value}))
    assert result.ok
    assert result.data == {"level": expected_level, "muted": expected_muted}


async def test_launch(registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend) -> None:
    data = {"type": "launch", "path": "%WINDIR%\\notepad.exe", "args": ["a b.txt"], "cwd": "C:\\"}
    assert (await runner.run(action(registry, data))).ok
    # El fake recibe los datos tal cual: la expansión de %VARIABLES% la hace el backend real.
    assert backend.calls == [("open_path", ("%WINDIR%\\notepad.exe", ("a b.txt",), "C:\\"))]


async def test_url_allowed_and_blocked(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    assert (await runner.run(action(registry, {"type": "url", "url": "spotify:playlist:1"}))).ok
    assert (await runner.run(action(registry, {"type": "url", "url": "steam://rungameid/570"}))).ok
    blocked = await runner.run(action(registry, {"type": "url", "url": "ms-msdt:/id"}))
    assert not blocked.ok and "no está permitido" in blocked.message
    file_url = await runner.run(action(registry, {"type": "url", "url": "file:///C:/x.bat"}))
    assert not file_url.ok
    assert backend.names() == ["open_uri", "open_uri"]


async def test_keys(registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend) -> None:
    await runner.run(action(registry, {"type": "keys", "combo": "win+d"}))
    await runner.run(action(registry, {"type": "keys", "text": "hola ñ"}))
    assert backend.calls == [("send_combo", ("win+d",)), ("type_text", ("hola ñ",))]


async def test_macro_runs_steps_in_order(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    macro = action(
        registry,
        {
            "type": "macro",
            "steps": [
                {"type": "launch", "path": "obs64.exe"},
                {"type": "wait", "ms": 5},
                {"type": "keys", "combo": "ctrl+shift+r"},
            ],
        },
    )
    assert (await runner.run(macro)).ok
    assert backend.names() == ["open_path", "send_combo"]


async def test_macro_stops_on_error(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    macro = action(
        registry,
        {
            "type": "macro",
            "steps": [
                {"type": "url", "url": "ms-msdt:/x"},
                {"type": "keys", "combo": "a"},
            ],
        },
    )
    result = await runner.run(macro)
    assert not result.ok and result.message.startswith("Paso 1 (url)")
    assert backend.calls == []


async def test_macro_depth_limit(registry: PluginRegistry, runner: ActionRunner) -> None:
    inner: dict[str, Any] = {"type": "media", "command": "next"}
    for _ in range(5):
        inner = {"type": "macro", "steps": [inner]}
    result = await runner.run(action(registry, inner))
    assert not result.ok and "niveles" in result.message


async def test_platform_error_becomes_failure(
    registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend
) -> None:
    backend.fail_with = "No se encontró el archivo"
    result = await runner.run(action(registry, {"type": "launch", "path": "x.exe"}))
    assert not result.ok and result.message == "No se encontró el archivo"


async def test_running_key_prevents_double_run(
    registry: PluginRegistry, runner: ActionRunner
) -> None:
    import asyncio

    slow = action(registry, {"type": "wait", "ms": 50})
    first = asyncio.create_task(runner.run(slow, key="p/b"))
    await asyncio.sleep(0)
    second = await runner.run(slow, key="p/b")
    assert not second.ok and "ya se está ejecutando" in second.message
    assert (await first).ok


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"type": "system", "command": "lock"}, False),
        ({"type": "system", "command": "shutdown"}, True),
        ({"type": "macro", "steps": [{"type": "system", "command": "restart"}]}, True),
        ({"type": "macro", "steps": [{"type": "media", "command": "next"}]}, False),
    ],
)
def test_requires_confirmation(
    registry: PluginRegistry, runner: ActionRunner, data: dict[str, Any], expected: bool
) -> None:
    assert runner.requires_confirmation(action(registry, data)) is expected


async def test_system(registry: PluginRegistry, runner: ActionRunner, backend: FakeBackend) -> None:
    await runner.run(action(registry, {"type": "system", "command": "monitor_off"}))
    assert backend.calls == [("system_command", (SystemCommand.MONITOR_OFF,))]


def test_registry_describe_has_schemas(registry: PluginRegistry) -> None:
    described = {p["type"]: p for p in registry.describe()}
    assert set(described) >= {"media", "launch", "url", "keys", "macro", "volume", "system", "wait"}
    assert "command" in described["media"]["schema"]["properties"]


async def test_external_plugin_loader(
    tmp_path: Path, registry: PluginRegistry, runner: ActionRunner
) -> None:
    repo_plugins = Path(__file__).resolve().parents[1] / "plugins"
    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')", encoding="utf-8")
    (tmp_path / "_private.py").write_text("raise RuntimeError('no se carga')", encoding="utf-8")
    added = load_external_plugins(registry, [repo_plugins, tmp_path, tmp_path / "no-existe"])
    assert added == ["hello"]  # el roto se omite sin romper el arranque
    result = await runner.run(registry.validate({"type": "hello", "name": "Redmi"}))
    assert result.ok and result.message == "¡Hola, Redmi!"
    # Un plugin externo no puede reemplazar un tipo ya registrado (p. ej. "launch")
    (tmp_path / "evil.py").write_text(
        "from phonedeck.plugins.launch import LaunchPlugin\nPLUGINS = [LaunchPlugin()]\n",
        encoding="utf-8",
    )
    assert load_external_plugins(registry, [tmp_path]) == []
    assert type(registry.get("launch")).__module__ == "phonedeck.plugins.launch"
