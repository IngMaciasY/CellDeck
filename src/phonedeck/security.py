"""Seguridad: tokens firmados, emparejamiento por PIN y validación de la cabecera Host.

Modelo de amenazas resumido (ver docs/seguridad.md):

- Por defecto el servidor solo escucha en 127.0.0.1 (modo USB con ``adb reverse``).
- Toda petición que ejecuta o modifica algo exige la cabecera ``X-PhoneDeck-Token``.
  Una web maliciosa abierta en el navegador de la PC no puede añadir esa cabecera a
  peticiones cross-origin sin CORS (y no hay CORS), así que no puede disparar acciones.
- Se valida ``Host`` para impedir ataques de *DNS rebinding*.
- Desde loopback el token se obtiene sin PIN; desde la red hace falta el PIN.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

log = logging.getLogger(__name__)

TOKEN_HEADER = "x-phonedeck-token"  # noqa: S105 - nombre de cabecera, no un secreto


# --------------------------------------------------------------------- tokens
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True, slots=True)
class TokenPayload:
    device: str
    issued_at: int
    expires_at: int


class TokenManager:
    """Emite y verifica tokens ``payload.firma`` (HMAC-SHA256).

    Revocar todos los dispositivos = rotar el secreto en ``settings.json``.
    """

    def __init__(self, secret_provider: Callable[[], str]) -> None:
        self._secret = secret_provider

    def _sign(self, payload_b64: str) -> str:
        key = self._secret().encode("utf-8")
        return _b64e(hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest())

    def issue(self, device: str, ttl_days: int) -> str:
        now = int(time.time())
        payload = {
            "v": 1,
            "dev": device[:64],
            "iat": now,
            "exp": now + ttl_days * 86400,
            "n": secrets.token_hex(4),
        }
        payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify(self, token: str | None) -> TokenPayload | None:
        if not token or token.count(".") != 1 or len(token) > 512:
            return None
        payload_b64, signature = token.split(".")
        if not hmac.compare_digest(signature, self._sign(payload_b64)):
            return None
        try:
            data = json.loads(_b64d(payload_b64))
            result = TokenPayload(str(data["dev"]), int(data["iat"]), int(data["exp"]))
        except (ValueError, KeyError, TypeError):
            return None
        if result.expires_at < time.time():
            return None
        return result


# ----------------------------------------------------------------- PIN/limit
class PairingLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Demasiados intentos. Reintenta en {retry_after} s")
        self.retry_after = retry_after


@dataclass
class PinGuard:
    """Limita los intentos de PIN por IP y globalmente (fuerza bruta distribuida)."""

    max_fails_per_ip: int = 5
    lock_seconds: int = 60
    max_fails_global: int = 20
    global_window: int = 600
    _fails: dict[str, list[float]] = field(default_factory=dict)
    _locked_until: dict[str, float] = field(default_factory=dict)
    _global: list[float] = field(default_factory=list)

    def check(self, ip: str) -> None:
        now = time.monotonic()
        until = max(self._locked_until.get(ip, 0.0), self._locked_until.get("*", 0.0))
        if until > now:
            raise PairingLocked(int(until - now) + 1)

    def verify(self, ip: str, pin: str, expected: str) -> bool:
        self.check(ip)
        if hmac.compare_digest(pin.encode("utf-8"), expected.encode("utf-8")):
            self._fails.pop(ip, None)
            return True
        now = time.monotonic()
        fails = [t for t in self._fails.get(ip, []) if now - t < self.lock_seconds * 10] + [now]
        self._fails[ip] = fails
        self._global = [t for t in self._global if now - t < self.global_window] + [now]
        if len(fails) >= self.max_fails_per_ip:
            self._locked_until[ip] = now + self.lock_seconds
            self._fails[ip] = []
            log.warning("PIN: IP %s bloqueada %ss tras varios fallos", ip, self.lock_seconds)
        if len(self._global) >= self.max_fails_global:
            self._locked_until["*"] = now + self.lock_seconds * 5
            self._global = []
            log.warning("PIN: emparejamiento bloqueado globalmente por exceso de fallos")
        return False


# ---------------------------------------------------------------- Host check
def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def strip_port(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6: [::1]:8765
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class HostCheckMiddleware:
    """Rechaza peticiones HTTP/WebSocket cuyo ``Host`` no sea de esta máquina."""

    def __init__(self, app: ASGIApp, allowed_hosts: Callable[[], set[str]]) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = strip_port(Headers(scope=scope).get("host", ""))
        if host in self.allowed_hosts():
            await self.app(scope, receive, send)
            return
        log.warning("Petición rechazada por Host no permitido: %r", host)
        if scope["type"] == "websocket":
            await WebSocketClose(code=1008)(scope, receive, send)
        else:
            await PlainTextResponse("Host no permitido", status_code=421)(scope, receive, send)
