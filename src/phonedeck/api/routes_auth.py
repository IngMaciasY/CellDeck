"""Sesión y emparejamiento por PIN."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from phonedeck.api.deps import StateDep, client_ip
from phonedeck.security import TOKEN_HEADER, PairingLocked, is_loopback
from phonedeck.state import AppState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["auth"])


def _session_info(state: AppState, loopback: bool) -> dict[str, Any]:
    return {
        "version": state.version,
        "mode": state.mode,
        "loopback": loopback,
        "can_edit": loopback or state.settings.allow_remote_edit,
        "backend": state.backend.name,
    }


@router.get("/session")
def session(request: Request, state: StateDep) -> dict[str, Any]:
    """Desde loopback (PC o USB con adb reverse) entrega un token directamente.

    Desde la red solo confirma un token existente; si no hay, responde 401 y la UI
    muestra la pantalla de PIN.
    """
    loopback = is_loopback(client_ip(request))
    if loopback:
        token = state.tokens.issue("local", state.settings.token_ttl_days)
        return {"token": token, **_session_info(state, True)}
    if state.tokens.verify(request.headers.get(TOKEN_HEADER)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Emparejamiento requerido")
    return _session_info(state, False)


class PairRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=12)
    device: str = Field(default="celular", max_length=64)


@router.post("/pair")
def pair(body: PairRequest, request: Request, state: StateDep) -> dict[str, Any]:
    """Canjea el PIN por un token (con límite de intentos)."""
    ip = client_ip(request)
    try:
        ok = state.pin_guard.verify(ip, body.pin.strip(), state.settings.pin)
    except PairingLocked as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    if not ok:
        log.warning("PIN incorrecto desde %s", ip)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PIN incorrecto")
    log.info("Dispositivo emparejado desde %s (%s)", ip, body.device)
    token = state.tokens.issue(body.device, state.settings.token_ttl_days)
    return {"token": token, **_session_info(state, is_loopback(ip))}
