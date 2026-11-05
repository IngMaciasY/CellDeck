"""Contrato de la capa nativa (Windows) que usan plugins y servicios.

Ningún plugin llama a Win32/WinRT directamente: todo pasa por un objeto que cumple
``PlatformBackend``. Así podemos sustituir la implementación real por ``FakeBackend``
en los tests o al desarrollar en un sistema que no es Windows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from phonedeck.platform.keymap import KeyCombo


class MediaKey(StrEnum):
    """Teclas multimedia estándar de Windows."""

    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREV = "prev"
    STOP = "stop"
    VOLUME_UP = "vol_up"
    VOLUME_DOWN = "vol_down"
    MUTE = "mute"


class SystemCommand(StrEnum):
    """Comandos de sistema soportados."""

    LOCK = "lock"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    MONITOR_OFF = "monitor_off"
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    LOGOFF = "logoff"


@dataclass(frozen=True, slots=True)
class VolumeState:
    """Estado del volumen maestro: ``level`` va de 0 a 100."""

    level: int
    muted: bool


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Información de la sesión multimedia actual ("ahora suena")."""

    title: str
    artist: str
    album: str = ""
    app_id: str = ""
    status: str = "unknown"  # playing | paused | stopped | unknown
    position_s: float | None = None
    duration_s: float | None = None
    artwork: bytes | None = field(default=None, repr=False, compare=False)
    artwork_hash: str | None = None


class PlatformError(Exception):
    """Error esperado de la capa nativa (mensaje apto para mostrar al usuario)."""


@runtime_checkable
class PlatformBackend(Protocol):
    """Operaciones nativas que PhoneDeck necesita. Todas son asíncronas."""

    name: str

    async def send_media_key(self, key: MediaKey) -> None:
        """Pulsa y suelta una tecla multimedia."""

    async def send_combo(self, combo: KeyCombo) -> None:
        """Pulsa una combinación de teclas (p. ej. Ctrl+Shift+Esc)."""

    async def type_text(self, text: str) -> None:
        """Escribe texto Unicode como si se tecleara."""

    async def open_path(self, path: str, args: Sequence[str] = (), cwd: str | None = None) -> None:
        """Abre un programa, documento o carpeta."""

    async def open_uri(self, uri: str) -> None:
        """Abre una URL o URI (``https:``, ``spotify:``, ``steam://``...)."""

    async def get_volume(self) -> VolumeState:
        """Devuelve el volumen maestro actual."""

    async def set_volume(self, level: int) -> None:
        """Fija el volumen maestro (0-100)."""

    async def set_mute(self, muted: bool) -> None:
        """Silencia o reactiva el audio."""

    async def get_now_playing(self) -> MediaInfo | None:
        """Devuelve la sesión multimedia actual o ``None`` si no hay ninguna."""

    async def system_command(self, command: SystemCommand) -> None:
        """Ejecuta un comando de sistema (bloquear, suspender, apagar...)."""

    async def close(self) -> None:
        """Libera recursos (hilos, COM...)."""
