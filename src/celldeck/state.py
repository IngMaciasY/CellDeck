"""Estado compartido de la aplicación y su construcción."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from celldeck import __version__
from celldeck.config.migrations import add_new_sections
from celldeck.config.settings import Settings, SettingsStore
from celldeck.config.store import ConfigStore
from celldeck.netinfo import AllowedHosts
from celldeck.obs import ObsBridge
from celldeck.platform import PlatformBackend, create_backend
from celldeck.plugins import PluginRegistry, build_default_registry
from celldeck.plugins.loader import load_external_plugins
from celldeck.plugins.runner import ActionRunner
from celldeck.pomodoro import PomodoroTimer
from celldeck.security import PinGuard, TokenManager
from celldeck.spotify import SpotifyBridge
from celldeck.ws import WebSocketHub

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Artwork:
    """Portada actual de "ahora suena" (se sirve en /api/media/artwork)."""

    hash: str
    data: bytes
    mime: str


@dataclass
class LiveState:
    """Estado en vivo compartido entre servicios y rutas."""

    artwork: Artwork | None = None
    # Clave de cada app del mezclador → su ejecutable. El celular solo conoce la clave.
    audio_paths: dict[str, str] = field(default_factory=dict)


@dataclass
class AppState:
    """Todo lo que necesitan las rutas y servicios. Se guarda en ``app.state.pd``."""

    data_dir: Path
    settings_store: SettingsStore
    config_store: ConfigStore
    registry: PluginRegistry
    backend: PlatformBackend
    runner: ActionRunner
    hub: WebSocketHub
    tokens: TokenManager
    pin_guard: PinGuard
    allowed_hosts: AllowedHosts
    pomodoro: PomodoroTimer
    obs: ObsBridge
    spotify: SpotifyBridge
    mode: str
    version: str = __version__
    started_at: float = field(default_factory=time.time)
    live: LiveState = field(default_factory=LiveState)
    # Bucle de eventos del servidor (se fija al arrancar). La bandeja vive en otro hilo y
    # lo usa para ejecutar corrutinas de forma segura.
    loop: asyncio.AbstractEventLoop | None = None
    # Notificación de Windows ``(mensaje, título)``: la pone la bandeja si la hay.
    notifier: Callable[[str, str], None] | None = None

    @property
    def settings(self) -> Settings:
        return self.settings_store.settings

    def run_threadsafe(self, coro: Coroutine[Any, Any, Any], timeout: float = 5.0) -> Any:
        """Ejecuta una corrutina en el bucle del servidor desde otro hilo (la bandeja)."""
        if self.loop is None or self.loop.is_closed():
            coro.close()
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout)


def build_state(
    data_dir: Path,
    *,
    backend: PlatformBackend | None = None,
    fake: bool = False,
    mode_override: str | None = None,
    plugin_dirs: list[Path] | None = None,
) -> AppState:
    """Carga settings y config, registra plugins y crea el backend."""
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_store = SettingsStore(data_dir / "settings.json")
    settings = settings_store.load()
    mode = mode_override or settings.mode

    registry = build_default_registry()
    if settings.load_external_plugins and plugin_dirs:
        load_external_plugins(registry, plugin_dirs)

    config_store = ConfigStore(data_dir / "config.json", registry)
    config_store.load()
    add_new_sections(config_store, settings_store)

    backend = backend or create_backend(fake=fake)
    log.info("Backend de plataforma: %s", backend.name)
    hub = WebSocketHub()
    pomodoro = PomodoroTimer(data_dir / "pomodoro.json")
    hub.set_provider("pomodoro", pomodoro.payload)
    spotify = SpotifyBridge(hub, settings_store)
    hub.set_provider("spotify", spotify.payload)
    # Quitar el widget retira el acceso: también a los datos en vivo de la cuenta.
    hub.set_gate("spotify", lambda: config_store.config.has_widget("spotify"))
    return AppState(
        data_dir=data_dir,
        settings_store=settings_store,
        config_store=config_store,
        registry=registry,
        backend=backend,
        runner=ActionRunner(registry, backend, lambda: settings_store.settings),
        hub=hub,
        tokens=TokenManager(lambda: settings_store.settings.secret),
        pin_guard=PinGuard(),
        allowed_hosts=AllowedHosts(mode == "wifi", settings.extra_allowed_hosts),
        pomodoro=pomodoro,
        obs=ObsBridge(hub, lambda: settings_store.settings),
        spotify=spotify,
        mode=mode,
    )
