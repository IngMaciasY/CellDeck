from __future__ import annotations

import pytest

from celldeck.platform.keymap import VK_CONTROL, VK_LWIN, VK_SHIFT, parse_combo


def test_parse_basic_combo() -> None:
    combo = parse_combo("Ctrl + Shift + Esc")
    assert combo.keys == (VK_CONTROL, VK_SHIFT, 0x1B)
    assert combo.text == "ctrl+shift+esc"


def test_modifiers_are_pressed_first() -> None:
    assert parse_combo("d+win").keys == (VK_LWIN, ord("D"))


@pytest.mark.parametrize(
    "name,vk", [("f5", 0x74), ("f24", 0x87), ("numpad0", 0x60), ("plus", 0xBB)]
)
def test_named_keys(name: str, vk: int) -> None:
    assert parse_combo(name).keys == (vk,)


@pytest.mark.parametrize(
    "combo,error",
    [
        ("", "vacía"),
        ("ctrl+", "mal formada"),
        ("ctrl+ctlr", "desconocida"),
        ("ctrl+control", "repetida"),
        ("a+b+c+d+e+f+g", "Máximo"),
    ],
)
def test_invalid_combos(combo: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_combo(combo)
