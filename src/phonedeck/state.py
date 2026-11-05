"""Estado compartido de la aplicación y su construcción."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from phonedeck import __version__
from phonedeck.config.settings import Settings, SettingsStore
from phonedeck.config.store import ConfigStore
from phonedeck.netinfo import AllowedHosts
from phonedeck.platform import PlatformBackend, create_backend
from phonedeck.plugins import PluginRegistry, build_default_registry
from phonedeck.plugins.loader import load_external_plugins
from phonedeck.plugins.runner import ActionRunner
from phonedeck.security import PinGuard, TokenManager
from phonedeck.ws import WebSocketHub

log = logging.getLogger(__name__)


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
    mode: str
    version: str = __version__
    started_at: float = field(default_factory=time.time)

    @property
    def settings(self) -> Settings:
        return self.settings_store.settings


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

    backend = backend or create_backend(fake=fake)
    log.info("Backend de plataforma: %s", backend.name)
    return AppState(
        data_dir=data_dir,
        settings_store=settings_store,
        config_store=config_store,
        registry=registry,
        backend=backend,
        runner=ActionRunner(registry, backend, lambda: settings_store.settings),
        hub=WebSocketHub(),
        tokens=TokenManager(lambda: settings_store.settings.secret),
        pin_guard=PinGuard(),
        allowed_hosts=AllowedHosts(mode == "wifi", settings.extra_allowed_hosts),
        mode=mode,
    )
