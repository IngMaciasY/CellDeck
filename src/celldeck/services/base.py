"""Base de los servicios de sondeo (pollers)."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from celldeck.state import AppState

MAX_BACKOFF_S = 30.0


class Poller(ABC):
    """Ejecuta ``tick()`` periódicamente, solo cuando alguien necesita el dato.

    - ``topic``: tema del WebSocket que publica. Si ningún cliente está suscrito (ningún
      celular muestra ese widget), no se consulta a Windows.
    - Con suscriptores usa ``interval``; sin ellos espera ``idle_interval``, pero se
      despierta al instante cuando un cliente se suscribe.
    - Si ``tick()`` falla repetidamente, espera cada vez más (hasta 30 s) y solo
      registra la traza completa la primera vez para no inundar el log.
    """

    name: ClassVar[str]
    topic: ClassVar[str | None] = None
    interval: ClassVar[float] = 1.0
    idle_interval: ClassVar[float] = 5.0

    def __init__(self, state: AppState) -> None:
        self.state = state
        self.log = logging.getLogger(f"celldeck.services.{self.name}")
        self.errors = 0

    @abstractmethod
    async def tick(self) -> None:
        """Una iteración: leer el estado y difundirlo si cambió."""

    def wanted(self) -> bool:
        return self.topic is None or self.state.hub.subscribers(self.topic) > 0

    def next_delay(self) -> float:
        base = self.interval if self.wanted() else self.idle_interval
        if self.errors:
            return min(MAX_BACKOFF_S, base * float(2 ** min(self.errors, 5)))
        return base

    async def run(self) -> None:
        self.log.debug("Servicio %s iniciado", self.name)
        while True:
            if self.wanted():
                try:
                    await self.tick()
                    if self.errors:
                        self.log.info("Servicio %s recuperado", self.name)
                    self.errors = 0
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.errors += 1
                    if self.errors == 1:
                        self.log.exception("Fallo en el servicio %s", self.name)
                    else:
                        self.log.debug("Fallo %d en %s", self.errors, self.name, exc_info=True)
            await self.state.hub.wait_for_change(self.next_delay())
