"""Servicio de estadísticas: uso de CPU y RAM (psutil)."""

from __future__ import annotations

import asyncio
from typing import Any

import psutil

from phonedeck.services.base import Poller

GIB = 1024**3


def read_stats() -> dict[str, Any]:
    """Lectura no bloqueante: cpu_percent(None) compara con la llamada anterior."""
    mem = psutil.virtual_memory()
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "ram": round(mem.percent, 1),
        "ram_used": round((mem.total - mem.available) / GIB, 2),
        "ram_total": round(mem.total / GIB, 2),
    }


class StatsService(Poller):
    name = "stats"
    topic = "stats"
    interval = 2.0
    idle_interval = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        psutil.cpu_percent(interval=None)  # la primera lectura siempre es 0: se descarta
        self._primed = False

    async def tick(self) -> None:
        if not self._primed:
            # cpu_percent mide desde la llamada anterior: sin margen devolvería 0.0.
            await asyncio.sleep(0.5)
            self._primed = True
        await self.state.hub.broadcast("stats", read_stats())


async def stats_service(state: Any) -> None:
    await StatsService(state).run()
