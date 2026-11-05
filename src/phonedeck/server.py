"""Factoría de la aplicación FastAPI y arranque de uvicorn."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from phonedeck.api import ROUTERS
from phonedeck.api.routes_config import config_payload
from phonedeck.config.models import Config
from phonedeck.live import handle_client_message
from phonedeck.security import HostCheckMiddleware, is_loopback
from phonedeck.state import AppState

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "media-src 'self' data: blob:; connect-src 'self' ws: wss:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
}

BackgroundTask = Callable[[AppState], Coroutine[Any, Any, None]]

# En Windows, ``mimetypes`` lee el registro y a veces asocia .js con text/plain; con
# "nosniff" Chrome bloquearía los scripts. Se fijan explícitamente.
_MIME_TYPES = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".webm": "video/webm",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
for _ext, _type in _MIME_TYPES.items():
    mimetypes.add_type(_type, _ext)


def create_app(
    state: AppState,
    web_dir: Path | None = None,
    background: list[BackgroundTask] | None = None,
) -> FastAPI:
    """Crea la app. ``background`` son corrutinas de larga duración (pollers)."""

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def on_config_change(_: Config) -> None:
            await state.hub.broadcast("config", config_payload(state))

        tasks = [
            asyncio.create_task(state.config_store.watch(on_config_change), name="config-watch")
        ]
        tasks += [asyncio.create_task(fn(state), name=fn.__name__) for fn in background or []]
        log.info("PhoneDeck %s listo (modo %s)", state.version, state.mode)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await state.hub.close_all()
            await state.backend.close()
            log.info("PhoneDeck detenido")

    app = FastAPI(
        title="PhoneDeck",
        version=state.version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.pd = state

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.path.startswith("/api/"):
            # Por defecto la API no se cachea (la portada fija su propia política).
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            # Revalidar siempre (ETag): tras actualizar PhoneDeck el celular no usa JS viejo.
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    # Se añade al final para que sea la capa más externa.
    app.add_middleware(HostCheckMiddleware, allowed_hosts=state.allowed_hosts)

    for router in ROUTERS:
        app.include_router(router)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"ok": True, "version": state.version}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        # Los navegadores no permiten cabeceras en WebSocket: el token va en la query.
        payload = state.tokens.verify(ws.query_params.get("token"))
        if payload is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        loopback = is_loopback(ws.client.host if ws.client else None)
        await ws.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "data": {
                        "version": state.version,
                        "mode": state.mode,
                        "can_edit": loopback or state.settings.allow_remote_edit,
                    },
                }
            )
        )
        await state.hub.register(ws)
        try:
            while True:
                msg = await ws.receive_text()
                await handle_client_message(state, ws, msg)
        except WebSocketDisconnect:
            pass
        finally:
            state.hub.unregister(ws)

    if web_dir is not None and web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    else:
        log.warning("No se encontró la carpeta web (%s): solo API", web_dir)
    return app


def run_server(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    """Crea el servidor uvicorn (bloqueante con ``server.run()``).

    ``log_config=None`` es imprescindible en el .exe sin consola (``sys.stdout`` es None).
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )
    return uvicorn.Server(config)
