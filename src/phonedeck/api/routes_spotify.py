"""Cuenta de Spotify y consulta de playlists.

Vincular la cuenta solo se puede desde la PC o con el celular por USB, porque Spotify exige que
el login vuelva a ``127.0.0.1``. Consultar las playlists se permite a cualquier celular
emparejado mientras exista el widget: si se quita, el celular pierde el acceso.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from phonedeck.api.deps import Principal, PrincipalDep, StateDep, client_ip
from phonedeck.security import TOKEN_HEADER, is_loopback
from phonedeck.spotify import (
    CLIENT_ID_PATTERN,
    IMAGE_KEY_PATTERN,
    PLAYLIST_ID_PATTERN,
    SpotifyError,
    SpotifyStatus,
    redirect_uri,
)
from phonedeck.state import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spotify", tags=["spotify"])

Offset = Annotated[int, Query(ge=0, le=100_000)]


def require_local(principal: PrincipalDep) -> Principal:
    if not principal.loopback:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "La cuenta de Spotify solo se configura desde la PC o con el celular por USB.",
        )
    return principal


def ensure_widget(state: AppState) -> None:
    if not state.config_store.config.has_widget("spotify"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No hay widget de Spotify")


def require_widget(state: StateDep, principal: PrincipalDep) -> Principal:
    ensure_widget(state)
    return principal


LocalDep = Annotated[Principal, Depends(require_local)]
ViewerDep = Annotated[Principal, Depends(require_widget)]


def callback_url(request: Request, state: AppState) -> str:
    return redirect_uri(request.url.port or state.settings.port)


def settings_payload(request: Request, state: AppState) -> dict[str, Any]:
    return {
        "client_id": state.settings.spotify_client_id,
        "redirect_uri": callback_url(request, state),
        "linked": bool(state.settings.spotify_refresh_token),
    }


class SpotifySettingsRequest(BaseModel):
    client_id: str = Field(pattern=CLIENT_ID_PATTERN)


@router.get("/settings")
def get_settings(request: Request, state: StateDep, _: LocalDep) -> dict[str, Any]:
    return settings_payload(request, state)


@router.put("/settings")
async def save_settings(
    body: SpotifySettingsRequest, request: Request, state: StateDep, who: LocalDep
) -> dict[str, Any]:
    await state.spotify.save_client_id(body.client_id.lower())
    log.info("Client ID de Spotify actualizado por %s", who.device)
    return settings_payload(request, state)


@router.post("/login")
def login(request: Request, state: StateDep, _: LocalDep) -> dict[str, str]:
    try:
        url = state.spotify.start_login(callback_url(request, state), str(request.base_url))
    except SpotifyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"url": url}


@router.post("/unlink")
async def unlink(request: Request, state: StateDep, who: LocalDep) -> dict[str, Any]:
    await state.spotify.unlink()
    log.info("Cuenta de Spotify desvinculada por %s", who.device)
    return settings_payload(request, state)


@router.get("/callback", include_in_schema=False)
async def callback(
    request: Request,
    state: StateDep,
    login_state: Annotated[str, Query(alias="state", max_length=128)] = "",
    code: Annotated[str, Query(max_length=2048)] = "",
    error: Annotated[str, Query(max_length=128)] = "",
) -> RedirectResponse:
    """Spotify devuelve aquí el navegador: no hay token de PhoneDeck, manda ``state``."""
    if not is_loopback(client_ip(request)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo desde esta PC")
    result, origin = await state.spotify.finish_login(login_state, code, error)
    return RedirectResponse(f"{origin}#spotify={result}", status.HTTP_303_SEE_OTHER)


def _unavailable(exc: SpotifyError) -> HTTPException:
    # No es 401: en el celular, un 401 significa que su sesión con PhoneDeck terminó.
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/playlists")
async def playlists(state: StateDep, _: ViewerDep, offset: Offset = 0) -> dict[str, Any]:
    try:
        return await state.spotify.playlists(offset)
    except SpotifyError as exc:
        raise _unavailable(exc) from exc


@router.get("/playlists/{playlist_id}/tracks")
async def playlist_tracks(
    playlist_id: Annotated[str, Path(pattern=PLAYLIST_ID_PATTERN)],
    state: StateDep,
    _: ViewerDep,
    offset: Offset = 0,
) -> dict[str, Any]:
    try:
        return await state.spotify.playlist_tracks(playlist_id, offset)
    except SpotifyError as exc:
        raise _unavailable(exc) from exc


@router.get("/image/{key}")
async def image(
    key: Annotated[str, Path(pattern=IMAGE_KEY_PATTERN)],
    request: Request,
    state: StateDep,
    token: str = "",
) -> Response:
    """Las etiquetas ``<img>`` no envían cabeceras: el token va también por query."""
    if state.tokens.verify(token or request.headers.get(TOKEN_HEADER)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o ausente")
    ensure_widget(state)
    try:
        found = await state.spotify.image(key)
    except SpotifyError as exc:
        raise _unavailable(exc) from exc
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin portada")
    data, mime = found
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


__all__ = ["SpotifyStatus", "router"]
