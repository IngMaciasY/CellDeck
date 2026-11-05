"""Portada de "ahora suena".

Las etiquetas ``<img>``/``background-image`` no pueden enviar cabeceras, así que aquí el
token se acepta también por query (``?token=``). La respuesta no revela nada más que la
portada que ya se muestra en el panel.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from phonedeck.api.deps import StateDep
from phonedeck.security import TOKEN_HEADER

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/artwork")
def artwork(request: Request, state: StateDep, h: str = "", token: str = "") -> Response:
    if state.tokens.verify(token or request.headers.get(TOKEN_HEADER)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o ausente")
    art = state.live.artwork
    if art is None or (h and h != art.hash):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin portada")
    # La URL incluye el hash: se puede cachear sin riesgo de mostrar una portada vieja.
    return Response(
        art.data, media_type=art.mime, headers={"Cache-Control": "private, max-age=86400"}
    )
