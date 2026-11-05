"""Capa de abstracción del sistema operativo."""

from __future__ import annotations

import logging
import sys

from phonedeck.platform.base import (
    MediaInfo,
    MediaKey,
    PlatformBackend,
    PlatformError,
    SystemCommand,
    VolumeState,
)
from phonedeck.platform.fake import FakeBackend

__all__ = [
    "FakeBackend",
    "MediaInfo",
    "MediaKey",
    "PlatformBackend",
    "PlatformError",
    "SystemCommand",
    "VolumeState",
    "create_backend",
]

log = logging.getLogger(__name__)


def create_backend(fake: bool = False) -> PlatformBackend:
    """Crea el backend adecuado. Fuera de Windows (o con ``fake=True``) usa el simulado."""
    if fake or sys.platform != "win32":
        if not fake:
            log.warning("Sistema no Windows: se usa el backend simulado")
        return FakeBackend()
    from phonedeck.platform.windows import WindowsBackend

    return WindowsBackend()
