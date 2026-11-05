"""Servicio de volumen: refleja en el celular los cambios hechos en la PC."""

from __future__ import annotations

from typing import Any

from phonedeck.platform.base import VolumeState
from phonedeck.services.base import Poller


def volume_payload(state: VolumeState) -> dict[str, Any]:
    return {"level": state.level, "muted": state.muted}


class VolumeService(Poller):
    name = "volume"
    interval = 1.0
    idle_interval = 5.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last: VolumeState | None = None

    async def tick(self) -> None:
        current = await self.state.backend.get_volume()
        if current != self._last:
            self._last = current
            await self.state.hub.broadcast("volume", volume_payload(current))


async def volume_service(state: Any) -> None:
    await VolumeService(state).run()
