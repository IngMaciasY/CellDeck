"""Servicio del mezclador: refleja en el celular las sesiones de audio de la PC."""

from __future__ import annotations

from typing import Any

from celldeck.platform.base import AudioApp, PlatformError
from celldeck.services.base import Poller


def mixer_payload(apps: list[AudioApp], error: str | None = None) -> dict[str, Any]:
    """Lo que ve el celular: sin rutas, solo si hay icono que pedir."""
    return {
        "apps": [
            {
                "key": app.key,
                "name": app.name,
                "level": app.level,
                "muted": app.muted,
                "icon": app.path is not None,
            }
            for app in apps
        ],
        "error": error,
    }


class MixerService(Poller):
    name = "mixer"
    topic = "mixer"
    interval = 1.0
    idle_interval = 5.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last: dict[str, Any] | None = None

    async def tick(self) -> None:
        apps: list[AudioApp] = []
        error: str | None = None
        try:
            apps = await self.state.backend.list_audio_apps()
        except PlatformError as exc:
            error = str(exc)
        self.state.live.audio_paths = {app.key: app.path for app in apps if app.path}
        payload = mixer_payload(apps, error)
        if payload != self._last:
            self._last = payload
            await self.state.hub.broadcast("mixer", payload)


async def mixer_service(state: Any) -> None:
    await MixerService(state).run()
