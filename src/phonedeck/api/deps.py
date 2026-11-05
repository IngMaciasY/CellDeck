"""Dependencias de FastAPI: estado y autenticación."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from phonedeck.security import TOKEN_HEADER, is_loopback
from phonedeck.state import AppState


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.pd
    return state


StateDep = Annotated[AppState, Depends(get_state)]


@dataclass(frozen=True, slots=True)
class Principal:
    """Quién hace la petición."""

    device: str
    loopback: bool
    can_edit: bool


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def get_principal(request: Request, state: StateDep) -> Principal:
    """Exige un token válido (incluso desde loopback, como protección CSRF)."""
    payload = state.tokens.verify(request.headers.get(TOKEN_HEADER))
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o ausente")
    loopback = is_loopback(client_ip(request))
    return Principal(
        device=payload.device,
        loopback=loopback,
        can_edit=loopback or state.settings.allow_remote_edit,
    )


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_editor(principal: PrincipalDep) -> Principal:
    if not principal.can_edit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "La edición remota está desactivada. Actívala desde la bandeja de la PC.",
        )
    return principal


EditorDep = Annotated[Principal, Depends(require_editor)]
