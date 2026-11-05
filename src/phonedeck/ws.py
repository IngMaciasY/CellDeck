"""Hub de WebSockets: difunde el estado en vivo (config, volumen, ahora suena, stats).

Suscripciones: cada cliente indica qué datos en vivo necesita según los widgets de la
página que está viendo (``{"type": "subscribe", "topics": ["media", "volume"]}``).
Solo recibe esos temas, y los servicios de la PC dejan de consultar a Windows los
datos que nadie está mirando.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

SEND_TIMEOUT_S = 5.0
# Temas filtrables; el resto de mensajes (config, hello, error) llega siempre a todos.
LIVE_TOPICS = frozenset({"media", "volume", "stats"})


class WebSocketHub:
    """Mantiene los clientes conectados, sus suscripciones y el último valor de cada tema.

    Al conectarse o suscribirse, un cliente recibe inmediatamente el último estado
    conocido, así la UI no espera al siguiente sondeo para mostrar algo.
    """

    def __init__(self) -> None:
        # Hasta que un cliente se suscribe explícitamente, recibe todos los temas
        # (compatibilidad con clientes antiguos).
        self._clients: dict[WebSocket, frozenset[str]] = {}
        self._snapshot: dict[str, Any] = {}
        self._wakeup = asyncio.Event()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def subscribers(self, topic: str) -> int:
        """Cuántos clientes quieren recibir ``topic``."""
        return sum(1 for topics in self._clients.values() if topic in topics)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._snapshot)

    async def wait_for_change(self, max_wait: float) -> None:
        """Duerme hasta ``max_wait`` segundos o hasta que cambien las suscripciones."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(max_wait):
                await self._wakeup.wait()
        self._wakeup.clear()

    def _wake(self) -> None:
        self._wakeup.set()

    async def register(self, ws: WebSocket) -> None:
        self._clients[ws] = LIVE_TOPICS
        log.info("Cliente WebSocket conectado (%d en total)", len(self._clients))
        for msg_type, data in self._snapshot.items():
            await self._send(ws, msg_type, data)
        self._wake()

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._clients:
            del self._clients[ws]
            log.info("Cliente WebSocket desconectado (%d en total)", len(self._clients))

    async def subscribe(self, ws: WebSocket, topics: set[str]) -> None:
        """Cambia los temas del cliente y le envía el último valor de los nuevos."""
        if ws not in self._clients:
            return
        wanted = frozenset(topics & LIVE_TOPICS)
        added = wanted - self._clients[ws]
        self._clients[ws] = wanted
        for topic in sorted(added):
            if topic in self._snapshot:
                await self._send(ws, topic, self._snapshot[topic])
        if added:
            self._wake()  # que los servicios lean ya el dato en vez de esperar

    async def broadcast(self, msg_type: str, data: Any, cache: bool = True) -> None:
        """Envía ``{"type": msg_type, "data": data}`` a los clientes interesados."""
        if cache:
            self._snapshot[msg_type] = data
        filtered = msg_type in LIVE_TOPICS
        clients = [ws for ws, topics in self._clients.items() if not filtered or msg_type in topics]
        if not clients:
            return
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
