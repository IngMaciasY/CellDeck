"""Parser de config.json: casos válidos e inválidos."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from phonedeck.config.models import ButtonItem, Config
from phonedeck.config.store import ConfigError, ConfigStore, default_config_data
from phonedeck.plugins import PluginRegistry
from phonedeck.plugins.keys import KeysParams
from phonedeck.plugins.macro import MacroParams


def parse(registry: PluginRegistry, data: Any) -> Config:
    # El constructor de ConfigStore no toca el disco; solo usamos su parser.
    return ConfigStore(Path("no-se-usa.json"), registry).parse(data)


def minimal(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "pages": [
            {
                "id": "p",
                "name": "P",
                "items": [{"kind": "button", "id": "b", "label": "B", "action": action}],
            }
        ]
    }


def test_default_config_is_valid(registry: PluginRegistry) -> None:
    config = parse(registry, default_config_data())
    assert [p.id for p in config.pages] == ["media", "pc", "mixer", "pomodoro", "obs", "spotify"]
    item = config.find_item("pc", "notepad-demo")
    assert isinstance(item, ButtonItem)
    assert isinstance(item.action, MacroParams)
    assert [s.type for s in item.action.steps] == ["launch", "wait", "keys"]


def test_roundtrip_preserves_action_fields(registry: PluginRegistry) -> None:
    config = parse(registry, default_config_data())
    again = parse(registry, config.to_json_dict())
    assert again.to_json_dict() == config.to_json_dict()
    steps = again.to_json_dict()["pages"][1]["items"][6]["action"]["steps"]
    assert steps[2] == {"type": "keys", "text": "¡Hola desde PhoneDeck!"}


def test_keys_combo_is_normalized(registry: PluginRegistry) -> None:
    config = parse(registry, minimal({"type": "keys", "combo": "CTRL + Alt + T"}))
    item = config.find_item("p", "b")
    assert isinstance(item, ButtonItem) and isinstance(item.action, KeysParams)
    assert item.action.combo == "ctrl+alt+t"


@pytest.mark.parametrize(
    "action,fragment",
    [
        ({"type": "nope"}, "desconocido"),
        ({"type": "keys", "combo": "ctrl+ctlr"}, "Tecla desconocida"),
        ({"type": "keys"}, "exactamente uno"),
        ({"type": "keys", "combo": "a", "text": "b"}, "exactamente uno"),
        ({"type": "media", "command": "rewind"}, "media"),
        ({"type": "volume", "op": "set", "value": -5}, "entre 0 y 100"),
        ({"type": "url", "url": "no tiene esquema"}, "espacios"),
        ({"type": "launch", "path": ""}, "launch"),
        ({"type": "launch", "path": "a.exe", "rm": "-rf"}, "Extra inputs"),
        ({"type": "macro", "steps": []}, "macro"),
        ({"type": "macro", "steps": [{"type": "wait", "ms": 999999}]}, "wait"),
        ("texto", "objeto"),
    ],
)
def test_invalid_actions(registry: PluginRegistry, action: Any, fragment: str) -> None:
    with pytest.raises(ConfigError) as info:
        parse(registry, minimal(action))
    assert fragment in str(info.value)


def test_duplicate_ids_rejected(registry: PluginRegistry) -> None:
    data = minimal({"type": "media", "command": "next"})
    data["pages"][0]["items"].append(copy.deepcopy(data["pages"][0]["items"][0]))
    with pytest.raises(ConfigError, match="repetido"):
        parse(registry, data)
    data = minimal({"type": "media", "command": "next"})
    data["pages"].append(copy.deepcopy(data["pages"][0]))
    with pytest.raises(ConfigError, match="página repetido"):
        parse(registry, data)


@pytest.mark.parametrize(
    "patch",
    [
        {"color": "red"},
        {"id": "con espacios"},
        {"w": 9},
        {"icon": "../../etc"},
        {"label": "x" * 41},
    ],
)
def test_invalid_button_fields(registry: PluginRegistry, patch: dict[str, Any]) -> None:
    data = minimal({"type": "media", "command": "next"})
    data["pages"][0]["items"][0].update(patch)
    with pytest.raises(ConfigError):
        parse(registry, data)


def test_widget_and_pages_required(registry: PluginRegistry) -> None:
    with pytest.raises(ConfigError):
        parse(registry, {"pages": []})
    ok = {
        "pages": [
            {
                "id": "p",
                "name": "P",
                "items": [{"kind": "widget", "id": "c", "widget": "clock", "w": 2}],
            }
        ]
    }
    assert parse(registry, ok).pages[0].items[0].kind == "widget"
    ok["pages"][0]["items"][0]["widget"] = "weather"
    with pytest.raises(ConfigError):
        parse(registry, ok)


@pytest.mark.parametrize(
    "appearance,ok",
    [
        ({"layout": "auto", "button_size": 104}, True),
        ({"layout": "fixed", "columns_portrait": 4}, True),
        ({"layout": "grid"}, False),
        ({"button_size": 30}, False),
        ({"button_size": 500}, False),
    ],
)
def test_appearance_layout(registry: PluginRegistry, appearance: dict[str, Any], ok: bool) -> None:
    data = {"appearance": appearance, "pages": [{"id": "p", "name": "P", "items": []}]}
    if ok:
        assert parse(registry, data).appearance.layout in ("auto", "fixed")
    else:
        with pytest.raises(ConfigError):
            parse(registry, data)
