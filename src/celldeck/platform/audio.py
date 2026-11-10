"""Reglas del mezclador que no dependen de Windows (se pueden probar en cualquier sistema)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from celldeck.platform.base import AudioApp

SYSTEM_KEY = "system"


@dataclass(frozen=True, slots=True)
class SessionRow:
    """Una sesión de audio ya identificada. ``volume`` va de 0.0 a 1.0."""

    key: str
    name: str
    path: str | None
    volume: float
    muted: bool


def app_key(identifier: str) -> str:
    """Clave opaca de una aplicación: el celular nunca ve ni envía rutas."""
    return hashlib.sha256(identifier.lower().encode("utf-8")).hexdigest()[:16]


def group_sessions(rows: Iterable[SessionRow]) -> list[AudioApp]:
    """Una entrada por aplicación, ordenadas por nombre y con el sistema al final.

    Si sus sesiones difieren, se muestra el volumen más alto, y la aplicación solo cuenta
    como silenciada si lo están todas (si algo se oye, no debe aparecer como muda).
    """
    groups: dict[str, AudioApp] = {}
    for row in rows:
        level = round(row.volume * 100)
        seen = groups.get(row.key)
        if seen is not None:
            level = max(seen.level, level)
        muted = row.muted and (seen is None or seen.muted)
        groups[row.key] = AudioApp(row.key, row.name, level, muted, row.path)
    return sorted(groups.values(), key=lambda a: (a.key == SYSTEM_KEY, a.name.casefold()))
