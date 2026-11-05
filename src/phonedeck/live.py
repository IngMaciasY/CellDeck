"""Comandos en vivo que envían los widgets del celular por WebSocket.

Solo existen tres comandos, con parámetros acotados:

- ``volume.set``  ``{"value": 0..100}``   (slider del widget de volumen)
- ``volume.mute`` ``{"muted": bool}``     (botón del widget de volumen)
- ``media``       ``{"command": MediaKey}`` (controles del widget "ahora suena")

Y solo se aceptan si el widget correspondiente está en la configuración: si el usuario
quita el widget, el celular deja de poder usar ese control.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from phonedeck.platform.base import MediaKey, PlatformError
from phonedeck.services.volume import volume_payload
from phonedeck.state import AppState

log = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 4096


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VolumeSet(_Msg):
    value: int = Field(ge=0, le=100)


class VolumeMute(_Msg):
    muted: bool


class MediaCommand(_Msg):
    command: MediaKey


# tipo de mensaje → (modelo, widget requerido en la config)
COMMANDS: dict[str, tuple[type[_Msg], str]] = {
    "volume.set": (VolumeSet, "volume"),
    "volume.mute": (VolumeMute, "volume"),
    "media": (MediaCommand, "now_playing"),
}


async def _send(ws: WebSocket, msg_type: str, data: Any = None) -> None:
    await ws.send_text(json.dumps({"type": msg_type, "data": data}, ensure_ascii=False))


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

    backend = state.backend
    try:
        if isinstance(cmd, VolumeSet):
            await backend.set_volume(cmd.value)
        elif isinstance(cmd, VolumeMute):
            await backend.set_mute(cmd.muted)
        elif isinstance(cmd, MediaCommand):
            await backend.send_media_key(cmd.command)
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
