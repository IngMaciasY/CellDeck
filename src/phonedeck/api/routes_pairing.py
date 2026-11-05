"""Emparejamiento: PIN, URLs y código QR para la página /pair.html de la PC.

Estas rutas revelan el PIN, así que **solo responden a la propia PC** (loopback) y
además exigen el token (que una web externa no puede leer). Un celular por WiFi
nunca puede consultarlas.
"""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from phonedeck.api.deps import PrincipalDep, StateDep, client_ip
from phonedeck.netinfo import local_ipv4_addresses, primary_ipv4
from phonedeck.security import is_loopback
from phonedeck.state import AppState

router = APIRouter(prefix="/api/pairing", tags=["pairing"])


def pairing_urls(state: AppState, port: int) -> list[str]:
    """URLs para abrir desde el celular por WiFi (la principal primero)."""
    pin = state.settings.pin
    primary = primary_ipv4()
    ips = local_ipv4_addresses()
    ordered = ([primary] if primary else []) + [ip for ip in ips if ip != primary]
    return [f"http://{ip}:{port}/#pin={pin}" for ip in ordered]


def _require_local(request: Request) -> None:
    if not is_loopback(client_ip(request)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo disponible desde la propia PC")


def _port(request: Request, state: AppState) -> int:
    return request.url.port or state.settings.port


@router.get("")
def pairing_info(request: Request, state: StateDep, _: PrincipalDep) -> dict[str, Any]:
    _require_local(request)
    port = _port(request, state)
    return {
        "mode": state.mode,
        "pin": state.settings.pin,
        "port": port,
        "urls": pairing_urls(state, port) if state.mode == "wifi" else [],
        "usb_url": f"http://localhost:{port}",
        "allow_remote_edit": state.settings.allow_remote_edit,
    }


@router.get("/qr.png")
def pairing_qr(request: Request, state: StateDep, _: PrincipalDep, url: str = "") -> Response:
    """QR de una de las URLs de emparejamiento (no se generan QR de texto arbitrario)."""
    _require_local(request)
    if url not in pairing_urls(state, _port(request, state)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "URL de emparejamiento no válida")
    import qrcode

    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")
