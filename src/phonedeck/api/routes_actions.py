"""Ejecución de acciones. El cliente solo envía IDs: la acción sale de la config."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from phonedeck.api.deps import PrincipalDep, StateDep
from phonedeck.config.models import ButtonItem

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["actions"])


class RunRequest(BaseModel):
    page: str = Field(min_length=1, max_length=40)
    item: str = Field(min_length=1, max_length=40)
    confirmed: bool = False


@router.post("/run")
async def run_action(body: RunRequest, state: StateDep, who: PrincipalDep) -> dict[str, Any]:
    item = state.config_store.config.find_item(body.page, body.item)
    if not isinstance(item, ButtonItem):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Botón no encontrado")

    needs_confirm = item.confirm or state.runner.requires_confirmation(item.action)
    if needs_confirm and not body.confirmed:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            {"message": "Esta acción requiere confirmación", "confirm_required": True},
        )

    log.info("Ejecutando %s/%s (%s) para %s", body.page, body.item, item.action.type, who.device)
    result = await state.runner.run(item.action, key=f"{body.page}/{body.item}")
    return {"ok": result.ok, "message": result.message, "data": dict(result.data or {})}
