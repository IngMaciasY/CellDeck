"""Hub de WebSockets: difunde el estado en vivo (config, volumen, ahora suena, stats)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

SEND_TIMEOUT_S = 5.0


class WebSocketHub:
    """Mantiene los clientes conectados y el último valor de cada tipo de mensaje.

    Al conectarse, un cliente recibe inmediatamente el último estado conocido, así la
    UI no espera al siguiente sondeo para mostrar algo.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._snapshot: dict[str, Any] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._snapshot)

    async def register(self, ws: WebSocket) -> None:
        self._clients.add(ws)
        log.info("Cliente WebSocket conectado (%d en total)", len(self._clients))
        for msg_type, data in self._snapshot.items():
            await self._send(ws, msg_type, data)

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.discard(ws)
            log.info("Cliente WebSocket desconectado (%d en total)", len(self._clients))

    async def broadcast(self, msg_type: str, data: Any, cache: bool = True) -> None:
        """Envía ``{"type": msg_type, "data": data}`` a todos los clientes."""
        if cache:
            self._snapshot[msg_type] = data
        if not self._clients:
            return
        clients = list(self._clients)  # foto fija: el set puede cambiar durante el await
        results = await asyncio.gather(
            *(self._send(ws, msg_type, data) for ws in clients), return_exceptions=True
        )
        for ws, result in zip(clients, results, strict=True):
            if result is False or isinstance(result, BaseException):
                self.unregister(ws)

    @staticmethod
    async def _send(ws: WebSocket, msg_type: str, data: Any) -> bool:
        try:
            text = json.dumps({"type": msg_type, "data": data}, ensure_ascii=False)
            await asyncio.wait_for(ws.send_text(text), timeout=SEND_TIMEOUT_S)
            return True
        except Exception:
            log.debug("Fallo enviando a un cliente WebSocket", exc_info=True)
            return False

    async def close_all(self) -> None:
        for ws in list(self._clients):
            try:
                await ws.close(code=1001)
            except Exception:
                log.debug("Error cerrando WebSocket", exc_info=True)
        self._clients.clear()
