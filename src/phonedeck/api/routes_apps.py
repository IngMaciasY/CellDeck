"""Aplicaciones del catálogo e iconos de los botones.

``GET /api/icon/{page}/{item}`` devuelve el icono oficial de la app que abre ese botón
(extraído del .exe instalado). Igual que /api/run, solo acepta IDs de botones de la
config: nunca una ruta enviada por la red.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from phonedeck.api.deps import PrincipalDep, StateDep
from phonedeck.apps import APPS
from phonedeck.config.models import ButtonItem
from phonedeck.plugins.app import AppParams
from phonedeck.plugins.base import ActionParams
from phonedeck.plugins.launch import LaunchParams
from phonedeck.plugins.url import UrlParams
from phonedeck.security import TOKEN_HEADER
from phonedeck.state import AppState

router = APIRouter(prefix="/api", tags=["apps"])

ICON_SIZE = 160  # px: nítido hasta ~64 px CSS en pantallas de densidad 2,5x


@router.get("/apps")
async def list_apps(state: StateDep, _: PrincipalDep) -> dict[str, Any]:
    """Catálogo con el estado de instalación (para el editor visual)."""
    result = []
    for app_id, spec in APPS.items():
        location = await state.backend.find_app(app_id)
        result.append(
            {
                "id": app_id,
                "name": spec.name,
                "installed": location is not None,
                "source": location.source if location else None,
                "fallback_icon": spec.fallback_icon,
            }
        )
    return {"apps": result}


async def icon_target(state: AppState, action: ActionParams) -> str | None:
    """Ejecutable, ruta o URI del que sacar el icono de una acción."""
    if isinstance(action, AppParams):
        location = await state.backend.find_app(action.app)
        if location is None:
            return None
        return location.path or location.uri
    if isinstance(action, LaunchParams):
        return action.path
    if isinstance(action, UrlParams):
        return action.url
    for child in action.children():  # macro: la primera app/programa que abra
        target = await icon_target(state, child)
        if target:
            return target
    return None


@router.get("/icon/{page_id}/{item_id}")
async def button_icon(
    page_id: str, item_id: str, request: Request, state: StateDep, token: str = ""
) -> Response:
    # <img> no puede enviar cabeceras: el token también se acepta por query.
    if state.tokens.verify(token or request.headers.get(TOKEN_HEADER)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o ausente")
    item = state.config_store.config.find_item(page_id, item_id)
    if not isinstance(item, ButtonItem):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Botón no encontrado")
    target = await icon_target(state, item.action)
    png = await state.backend.target_icon(target, ICON_SIZE) if target else None
    if png is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin icono para esta acción")
    # La URL lleva la revisión de la config (?v=): se puede cachear sin riesgo.
    return Response(
        png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )
