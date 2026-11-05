"""Lectura y guardado de la configuración (usado por la UI y el editor)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from phonedeck.api.deps import EditorDep, PrincipalDep, StateDep
from phonedeck.config.store import ConfigConflictError, ConfigError
from phonedeck.platform.keymap import available_key_names
from phonedeck.state import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["config"])


def config_payload(state: AppState) -> dict[str, Any]:
    store = state.config_store
    return {
        "revision": store.revision,
        "config": store.config.to_json_dict(),
        "error": str(store.last_error) if store.last_error else None,
    }


@router.get("/config")
def get_config(state: StateDep, _: PrincipalDep) -> dict[str, Any]:
    return config_payload(state)


class SaveConfigRequest(BaseModel):
    revision: str | None = Field(default=None, max_length=64)
    config: dict[str, Any]


@router.put("/config")
async def save_config(body: SaveConfigRequest, state: StateDep, who: EditorDep) -> dict[str, Any]:
    """Valida y guarda la config completa. 409 si otra edición llegó antes."""
    store = state.config_store
    try:
        config = store.parse(body.config)
        store.save(config, expected_revision=body.revision)
    except ConfigError as exc:
        raise HTTPException(422, {"message": str(exc), "errors": exc.errors}) from None
    except ConfigConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    log.info("Config guardada por %s", who.device)
    payload = config_payload(state)
    await state.hub.broadcast("config", payload)
    return payload


class ValidateConfigRequest(BaseModel):
    config: dict[str, Any]


@router.post("/config/validate")
def validate_config(body: ValidateConfigRequest, state: StateDep, _: EditorDep) -> dict[str, Any]:
    """Valida sin guardar (el editor lo usa al terminar de editar un botón)."""
    try:
        state.config_store.parse(body.config)
    except ConfigError as exc:
        raise HTTPException(422, {"message": str(exc), "errors": exc.errors}) from None
    return {"ok": True}


@router.get("/plugins")
def list_plugins(state: StateDep, _: PrincipalDep) -> dict[str, Any]:
    """Tipos de acción disponibles con su esquema (para el editor visual)."""
    return {
        "plugins": state.registry.describe(),
        "keys": available_key_names(),
        "allowed_url_schemes": state.settings.allowed_url_schemes,
    }
