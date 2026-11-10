"""Traducción de combinaciones legibles ("ctrl+shift+esc") a códigos virtuales de Windows.

Este módulo es Python puro (no toca Win32) para poder validarlo en cualquier
plataforma y en los tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_KEYS_PER_COMBO = 6

# Modificadores genéricos (sirven tanto la tecla izquierda como la derecha).
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B

_NAMED_KEYS: dict[str, int] = {
    # Modificadores
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "shift": VK_SHIFT,
    "alt": VK_MENU,
    "win": VK_LWIN,
    "windows": VK_LWIN,
    "meta": VK_LWIN,
    "super": VK_LWIN,
    # Edición y navegación
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "menu": 0x5D,
    "apps": 0x5D,
    "numlock": 0x90,
    "scrolllock": 0x91,
    # Teclado numérico
    "multiply": 0x6A,
    "add": 0x6B,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    # Puntuación (distribución US; en otras distribuciones el carácter puede variar)
    "plus": 0xBB,
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "comma": 0xBC,
    "-": 0xBD,
    "minus": 0xBD,
    ".": 0xBE,
    "period": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
    # Multimedia
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
}

# Letras, dígitos, F1-F24 y numpad0-9
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    _NAMED_KEYS[_c] = ord(_c.upper())
for _i in range(1, 25):
    _NAMED_KEYS[f"f{_i}"] = 0x6F + _i
for _i in range(10):
    _NAMED_KEYS[f"numpad{_i}"] = 0x60 + _i

MODIFIER_VKS = frozenset({VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN})

# Teclas que requieren el flag KEYEVENTF_EXTENDEDKEY al simularlas.
EXTENDED_VKS = frozenset(
    {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}
    | set(range(0xA6, 0xB8))  # navegador, volumen y multimedia
)

_SPLIT_RE = re.compile(r"\s*\+\s*")


@dataclass(frozen=True, slots=True)
class KeyCombo:
    """Combinación ya resuelta: códigos VK en orden de pulsación."""

    keys: tuple[int, ...]
    text: str

    def __str__(self) -> str:
        return self.text


def available_key_names() -> list[str]:
    """Lista ordenada de nombres de tecla aceptados (para el editor)."""
    return sorted(_NAMED_KEYS)


def parse_combo(combo: str) -> KeyCombo:
    """Convierte ``"ctrl+shift+esc"`` en un :class:`KeyCombo`.

    Raises:
        ValueError: si la combinación está vacía, tiene teclas desconocidas,
            repetidas o demasiadas teclas.
    """
    raw = combo.strip().lower()
    if not raw:
        raise ValueError("La combinación de teclas está vacía")
    # "ctrl++" sería ambiguo: para la tecla '+' hay que escribir "plus".
    parts = [p for p in _SPLIT_RE.split(raw)]
    if any(not p for p in parts):
        raise ValueError("Combinación mal formada (usa 'plus' para la tecla +)")
    if len(parts) > MAX_KEYS_PER_COMBO:
        raise ValueError(f"Máximo {MAX_KEYS_PER_COMBO} teclas por combinación")

    vks: list[int] = []
    for part in parts:
        vk = _NAMED_KEYS.get(part)
        if vk is None:
            raise ValueError(f"Tecla desconocida: '{part}'")
        if vk in vks:
            raise ValueError(f"Tecla repetida: '{part}'")
        vks.append(vk)

    # Los modificadores siempre se pulsan primero, respetando el orden escrito.
    ordered = [v for v in vks if v in MODIFIER_VKS] + [v for v in vks if v not in MODIFIER_VKS]
    return KeyCombo(keys=tuple(ordered), text="+".join(parts))
