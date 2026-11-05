"""Base de los servicios de sondeo (pollers)."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from phonedeck.state import AppState

MAX_BACKOFF_S = 30.0


class Poller(ABC):
    """Ejecuta ``tick()`` periódicamente.

    - Con clientes conectados usa ``interval``; sin clientes, ``idle_interval``
      (ahorra CPU cuando nadie mira el panel).
    - Si ``tick()`` falla repetidamente, espera cada vez más (hasta 30 s) y solo
      registra la traza completa la primera vez para no inundar el log.
    """

    name: ClassVar[str]
    interval: ClassVar[float] = 1.0
    idle_interval: ClassVar[float] = 5.0

    def __init__(self, state: AppState) -> None:
        self.state = state
        self.log = logging.getLogger(f"phonedeck.services.{self.name}")
        self.errors = 0

    @abstractmethod
    async def tick(self) -> None:
        """Una iteración: leer el estado y difundirlo si cambió."""

    def next_delay(self) -> float:
        base = self.interval if self.state.hub.client_count else self.idle_interval
        if self.errors:
            return min(MAX_BACKOFF_S, base * float(2 ** min(self.errors, 5)))
        return base

    async def run(self) -> None:
        self.log.debug("Servicio %s iniciado", self.name)
        while True:
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
            await asyncio.sleep(self.next_delay())
