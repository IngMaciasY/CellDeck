"""Comandos en vivo que envían los widgets del celular por WebSocket.

Son pocos comandos, con parámetros acotados:

- ``volume.set``  ``{"value": 0..100}``   (slider del widget de volumen)
- ``volume.mute`` ``{"muted": bool}``     (botón del widget de volumen)
- ``media``       ``{"command": MediaKey}`` (controles del widget "ahora suena")
- ``mixer.set``   ``{"key": clave, "value": 0..100}`` (volumen de una aplicación)
- ``mixer.mute``  ``{"key": clave, "muted": bool}``   (silenciar una aplicación)
- ``pomodoro.control`` ``{"action": "start" | "pause" | "resume" | "reset"}``
- ``pomodoro.config``  ``{"work": min, "short_break": min, "long_break": min}``
- ``obs.scene``   ``{"name": escena}``    (solo escenas de la lista actual de OBS)
- ``spotify.control`` ``{"action": "play" | "pause" | "next" | "previous"}``
- ``spotify.play``    ``{"context": playlist o álbum, "track": canción, "uris": [canciones]}``
- ``spotify.queue``   ``{"uri": canción}`` (la añade a la cola)
- ``spotify.skip``    ``{"count": 1..20}`` (salta a esa canción de la cola)
- ``spotify.seek``    ``{"position_ms": 0..24 h}`` (avanza dentro de la canción)
- ``spotify.open``    ``{"uri": playlist o álbum}`` (lo abre en la PC)

Y solo se aceptan si el widget correspondiente está en la configuración: si el usuario
quita el widget, el celular deja de poder usar ese control.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Literal, Self

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from celldeck.platform.base import MediaKey, PlatformError
from celldeck.pomodoro import MAX_MINUTES, Durations
from celldeck.services.pomodoro import publish as publish_pomodoro
from celldeck.services.volume import volume_payload
from celldeck.spotify import (
    CONTEXT_URI_PATTERN,
    ITEM_URI_PATTERN,
    MAX_PLAY_URIS,
    MAX_POSITION_MS,
    QUEUE_LIMIT,
    MediaAction,
)
from celldeck.state import AppState

log = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 4096
APP_KEY_PATTERN = r"^[a-z0-9]{1,32}$"


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VolumeSet(_Msg):
    value: int = Field(ge=0, le=100)


class VolumeMute(_Msg):
    muted: bool


class MediaCommand(_Msg):
    command: MediaKey


class MixerSet(_Msg):
    key: str = Field(pattern=APP_KEY_PATTERN)
    value: int = Field(ge=0, le=100)


class MixerMute(_Msg):
    key: str = Field(pattern=APP_KEY_PATTERN)
    muted: bool


class PomodoroControl(_Msg):
    action: Literal["start", "pause", "resume", "reset"]


class PomodoroConfig(_Msg):
    work: int = Field(ge=1, le=MAX_MINUTES)
    short_break: int = Field(ge=1, le=MAX_MINUTES)
    long_break: int = Field(ge=1, le=MAX_MINUTES)


class ObsScene(_Msg):
    name: str = Field(min_length=1, max_length=256)


class _SpotifyMsg(_Msg):
    """Órdenes para Spotify: van por Internet y se ejecutan aparte."""


class SpotifyControl(_SpotifyMsg):
    action: MediaAction


class SpotifyPlay(_SpotifyMsg):
    context: str | None = Field(default=None, pattern=CONTEXT_URI_PATTERN)
    track: str | None = Field(default=None, pattern=ITEM_URI_PATTERN)
    uris: list[Annotated[str, Field(pattern=ITEM_URI_PATTERN)]] | None = Field(
        default=None, min_length=1, max_length=MAX_PLAY_URIS
    )

    @model_validator(mode="after")
    def _something_to_play(self) -> Self:
        if self.context is None and self.track is None and not self.uris:
            raise ValueError("Falta qué reproducir")
        return self


class SpotifyQueue(_SpotifyMsg):
    uri: str = Field(pattern=ITEM_URI_PATTERN)


class SpotifySeek(_SpotifyMsg):
    position_ms: int = Field(ge=0, le=MAX_POSITION_MS)


class SpotifyOpen(_SpotifyMsg):
    uri: str = Field(pattern=CONTEXT_URI_PATTERN)


class SpotifySkip(_SpotifyMsg):
    count: int = Field(ge=1, le=QUEUE_LIMIT)


# tipo de mensaje → (modelo, widget requerido en la config)
COMMANDS: dict[str, tuple[type[_Msg], str]] = {
    "volume.set": (VolumeSet, "volume"),
    "volume.mute": (VolumeMute, "volume"),
    "media": (MediaCommand, "now_playing"),
    "mixer.set": (MixerSet, "mixer"),
    "mixer.mute": (MixerMute, "mixer"),
    "pomodoro.control": (PomodoroControl, "pomodoro"),
    "pomodoro.config": (PomodoroConfig, "pomodoro"),
    "obs.scene": (ObsScene, "obs"),
    "spotify.control": (SpotifyControl, "spotify"),
    "spotify.play": (SpotifyPlay, "spotify"),
    "spotify.queue": (SpotifyQueue, "spotify"),
    "spotify.seek": (SpotifySeek, "spotify"),
    "spotify.skip": (SpotifySkip, "spotify"),
    "spotify.open": (SpotifyOpen, "spotify"),
}


# Referencias a las órdenes en curso: asyncio solo guarda una referencia débil a cada tarea.
_spotify_tasks: set[asyncio.Task[None]] = set()


async def _send(ws: WebSocket, msg_type: str, data: Any = None) -> None:
    await ws.send_text(json.dumps({"type": msg_type, "data": data}, ensure_ascii=False))


async def _run_spotify(state: AppState, ws: WebSocket, cmd: _Msg) -> None:
    """Ejecuta una orden para Spotify. Puede tardar segundos y va por Internet."""
    try:
        if isinstance(cmd, SpotifyControl):
            await state.spotify.control(cmd.action)
        elif isinstance(cmd, SpotifyPlay):
            await state.spotify.play(cmd.context, cmd.track, cmd.uris)
        elif isinstance(cmd, SpotifyQueue):
            await state.spotify.add_to_queue(cmd.uri)
        elif isinstance(cmd, SpotifySeek):
            await state.spotify.seek(cmd.position_ms)
        elif isinstance(cmd, SpotifySkip):
            await state.spotify.skip(cmd.count)
        elif isinstance(cmd, SpotifyOpen):
            await state.spotify.open_in_app(state.backend, cmd.uri)
    except PlatformError as exc:
        await _report(ws, str(exc))
    except Exception:
        log.exception("Error ejecutando una orden de Spotify")
        await _report(ws, "Error interno (ver log)")


async def _report(ws: WebSocket, message: str) -> None:
    try:
        await _send(ws, "error", {"message": message})
    except (RuntimeError, WebSocketDisconnect):
        log.debug("El celular se desconectó antes de recibir el error")


async def handle_client_message(state: AppState, ws: WebSocket, raw: str) -> None:
    """Procesa un mensaje del cliente. Los mensajes desconocidos se ignoran."""
    if len(raw) > MAX_MESSAGE_BYTES:
        return
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(msg, dict):
        return
    msg_type = msg.get("type")
    if msg_type == "ping":
        await ws.send_text('{"type":"pong"}')
        return
    if msg_type == "subscribe":
        topics = msg.get("topics")
        if isinstance(topics, list) and len(topics) <= 10:
            await state.hub.subscribe(ws, {t for t in topics if isinstance(t, str)})
        return
    if not isinstance(msg_type, str) or msg_type not in COMMANDS:
        return

    model, widget = COMMANDS[msg_type]
    if not state.config_store.config.has_widget(widget):
        await _send(ws, "error", {"message": f"Control no permitido: no hay widget '{widget}'"})
        return
    try:
        cmd = model.model_validate(msg)
    except ValidationError:
        await _send(ws, "error", {"message": "Comando inválido"})
        return

    if isinstance(cmd, _SpotifyMsg):
        # Aparte: si Spotify tarda, el volumen y demás controles de este celular no esperan.
        task = asyncio.create_task(_run_spotify(state, ws, cmd))
        _spotify_tasks.add(task)
        task.add_done_callback(_spotify_tasks.discard)
        return

    backend = state.backend
    try:
        if isinstance(cmd, VolumeSet):
            await backend.set_volume(cmd.value)
        elif isinstance(cmd, VolumeMute):
            await backend.set_mute(cmd.muted)
        elif isinstance(cmd, MediaCommand):
            await backend.send_media_key(cmd.command)
        elif isinstance(cmd, MixerSet):
            await backend.set_app_volume(cmd.key, cmd.value)
        elif isinstance(cmd, MixerMute):
            await backend.set_app_mute(cmd.key, cmd.muted)
            state.hub.wake()  # el botón debe reaccionar ya; el slider ya se mueve solo
        elif isinstance(cmd, PomodoroControl):
            getattr(state.pomodoro, cmd.action)()
            await publish_pomodoro(state)
        elif isinstance(cmd, PomodoroConfig):
            state.pomodoro.configure(Durations.model_validate(cmd.model_dump()))
            await publish_pomodoro(state)
        elif isinstance(cmd, ObsScene):
            await state.obs.set_scene(cmd.name)
    except PlatformError as exc:
        await _send(ws, "error", {"message": str(exc)})
        return
    except Exception:
        log.exception("Error ejecutando el comando en vivo %s", msg_type)
        await _send(ws, "error", {"message": "Error interno (ver log)"})
        return

    if msg_type.startswith("volume."):
        # Respuesta inmediata a todos los clientes, sin esperar al siguiente sondeo.
        await state.hub.broadcast("volume", volume_payload(await backend.get_volume()))
