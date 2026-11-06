"""Backend simulado: registra las llamadas en memoria en vez de tocar Windows.

Se usa en los tests y con ``python -m phonedeck --fake`` para desarrollar la UI
desde cualquier sistema operativo.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from phonedeck.platform.base import (
    AppLocation,
    AudioApp,
    MediaInfo,
    MediaKey,
    PlatformError,
    SystemCommand,
    VolumeState,
)
from phonedeck.platform.keymap import KeyCombo

log = logging.getLogger(__name__)

# (título, artista, duración en s) para el modo demo
_DEMO_TRACKS = (
    ("Canción de prueba", "PhoneDeck", 200.0),
    ("Otra canción", "Artista demo", 180.0),
    ("Tercera pista", "Modo --fake", 240.0),
)


class FakeBackend:
    """Implementación de ``PlatformBackend`` sin efectos secundarios."""

    name = "fake"

    def __init__(self, demo: bool = False) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.volume = VolumeState(level=50, muted=False)
        self.now_playing: MediaInfo | None = None
        self.audio_apps: dict[str, AudioApp] = {}
        self.fail_with: str | None = None  # si se fija, la siguiente llamada falla
        # Apps "instaladas" e iconos simulados (los tests los rellenan).
        self.apps: dict[str, AppLocation] = {}
        self.icons: dict[str, bytes] = {}
        # Modo demo (``--fake``): una "canción" que avanza y responde a los controles.
        self.demo = demo
        self._demo_track = 0
        self._demo_playing = True
        self._demo_started = time.monotonic()
        self._demo_offset = 0.0
        if demo:
            self.audio_apps = {
                "spotify": AudioApp("spotify", "Spotify", 80, False),
                "brave": AudioApp("brave", "Brave", 45, False),
                "discord": AudioApp("discord", "Discord", 100, True),
                "system": AudioApp("system", "Sonidos del sistema", 60, False),
            }

    # ------------------------------------------------------------- utilidades
    def _record(self, name: str, *args: Any) -> None:
        if self.fail_with is not None:
            msg, self.fail_with = self.fail_with, None
            raise PlatformError(msg)
        self.calls.append((name, args))
        log.debug("FakeBackend.%s%r", name, args)

    def names(self) -> list[str]:
        """Nombres de las llamadas registradas, en orden."""
        return [c[0] for c in self.calls]

    # ------------------------------------------------------- PlatformBackend
    async def send_media_key(self, key: MediaKey) -> None:
        self._record("send_media_key", key)
        if not self.demo:
            return
        if key is MediaKey.PLAY_PAUSE:
            self._demo_offset = self._demo_position()
            self._demo_started = time.monotonic()
            self._demo_playing = not self._demo_playing
        elif key in (MediaKey.NEXT, MediaKey.PREV):
            step = 1 if key is MediaKey.NEXT else -1
            self._demo_track = (self._demo_track + step) % len(_DEMO_TRACKS)
            self._demo_offset = 0.0
            self._demo_started = time.monotonic()
        elif key is MediaKey.MUTE:
            self.volume = VolumeState(self.volume.level, not self.volume.muted)
        elif key in (MediaKey.VOLUME_UP, MediaKey.VOLUME_DOWN):
            delta = 2 if key is MediaKey.VOLUME_UP else -2
            self.volume = VolumeState(max(0, min(100, self.volume.level + delta)), False)

    def _demo_position(self) -> float:
        elapsed = time.monotonic() - self._demo_started if self._demo_playing else 0.0
        return (self._demo_offset + elapsed) % _DEMO_TRACKS[self._demo_track][2]

    async def send_combo(self, combo: KeyCombo) -> None:
        self._record("send_combo", combo.text)

    async def type_text(self, text: str) -> None:
        self._record("type_text", text)

    async def open_path(self, path: str, args: Sequence[str] = (), cwd: str | None = None) -> None:
        self._record("open_path", path, tuple(args), cwd)

    async def open_uri(self, uri: str) -> None:
        self._record("open_uri", uri)

    async def get_volume(self) -> VolumeState:
        return self.volume

    async def set_volume(self, level: int) -> None:
        self._record("set_volume", level)
        self.volume = VolumeState(level=max(0, min(100, level)), muted=self.volume.muted)

    async def set_mute(self, muted: bool) -> None:
        self._record("set_mute", muted)
        self.volume = VolumeState(level=self.volume.level, muted=muted)

    async def list_audio_apps(self) -> list[AudioApp]:
        return list(self.audio_apps.values())

    def _audio_app(self, key: str) -> AudioApp:
        if key not in self.audio_apps:
            raise PlatformError("Esa aplicación ya no tiene audio")
        return self.audio_apps[key]

    async def set_app_volume(self, key: str, level: int) -> None:
        self._record("set_app_volume", key, level)
        self.audio_apps[key] = replace(self._audio_app(key), level=max(0, min(100, level)))

    async def set_app_mute(self, key: str, muted: bool) -> None:
        self._record("set_app_mute", key, muted)
        self.audio_apps[key] = replace(self._audio_app(key), muted=muted)

    async def get_now_playing(self) -> MediaInfo | None:
        if self.demo and self.now_playing is None:
            title, artist, duration = _DEMO_TRACKS[self._demo_track]
            return MediaInfo(
                title=title,
                artist=artist,
                app_id="PhoneDeck.Demo",
                status="playing" if self._demo_playing else "paused",
                position_s=self._demo_position(),
                duration_s=duration,
            )
        return self.now_playing

    async def system_command(self, command: SystemCommand) -> None:
        self._record("system_command", command)

    async def find_app(self, app_id: str) -> AppLocation | None:
        return self.apps.get(app_id)

    def forget_app(self, app_id: str) -> None:
        self.calls.append(("forget_app", (app_id,)))

    async def target_icon(self, target: str, size: int = 160) -> bytes | None:
        return self.icons.get(target)

    async def close(self) -> None:
        self.calls.append(("close", ()))
