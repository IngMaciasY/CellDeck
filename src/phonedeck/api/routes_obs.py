"""Ajustes de la conexión con OBS. Solo desde la propia PC o un celular por USB.

Como el resto de ``settings.json``, no se pueden cambiar desde la red. La contraseña es de
solo escritura: el servidor nunca la devuelve.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from phonedeck.api.deps import Principal, PrincipalDep, StateDep
from phonedeck.state import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/obs", tags=["obs"])


def require_local(principal: PrincipalDep) -> Principal:
    if not principal.loopback:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "La conexión con OBS solo se configura desde la PC o con el celular por USB.",
        )
    return principal


LocalDep = Annotated[Principal, Depends(require_local)]


def settings_payload(state: AppState) -> dict[str, Any]:
    settings = state.settings
    return {
        "host": settings.obs_host,
        "port": settings.obs_port,
        "has_password": bool(settings.obs_password),
    }


class ObsSettingsRequest(BaseModel):
    host: str = Field(pattern=r"^[A-Za-z0-9.-]{1,253}$")
    port: int = Field(ge=1, le=65535)
    # None: conservar la actual. Texto vacío: quitarla.
    password: str | None = Field(default=None, max_length=200)


@router.get("/settings")
def get_settings(state: StateDep, _: LocalDep) -> dict[str, Any]:
    return settings_payload(state)


@router.put("/settings")
async def save_settings(body: ObsSettingsRequest, state: StateDep, who: LocalDep) -> dict[str, Any]:
    changes: dict[str, Any] = {"obs_host": body.host, "obs_port": body.port}
    if body.password is not None:
        changes["obs_password"] = body.password
    state.settings_store.update(**changes)
    log.info("Conexión con OBS actualizada por %s", who.device)
    await state.obs.reconnect()
    return settings_payload(state)
