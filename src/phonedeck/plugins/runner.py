"""Ejecutor de acciones: aplica límites, captura errores y registra en el log."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from phonedeck.config.settings import Settings
from phonedeck.platform.base import PlatformBackend, PlatformError
from phonedeck.plugins.base import ActionParams, ActionResult, PluginContext, PluginRegistry

log = logging.getLogger(__name__)

MAX_DEPTH = 3  # macros dentro de macros
MAX_RUNTIME_S = 120.0  # tiempo máximo de una acción de primer nivel


class ActionRunner:
    """Ejecuta acciones validadas a través de su plugin."""

    def __init__(
        self,
        registry: PluginRegistry,
        backend: PlatformBackend,
        settings_provider: Callable[[], Settings],
    ) -> None:
        self.registry = registry
        self.backend = backend
        self._settings = settings_provider
        self._running: set[str] = set()

    def requires_confirmation(self, params: ActionParams) -> bool:
        """``True`` si la acción o alguna anidada (pasos de macro) es peligrosa."""
        if self.registry.get(params.type).needs_confirmation(params):
            return True
        return any(self.requires_confirmation(child) for child in params.children())

    def is_running(self, key: str) -> bool:
        return key in self._running

    async def run(self, params: ActionParams, key: str | None = None) -> ActionResult:
        """Ejecuta una acción de primer nivel.

        Args:
            params: acción ya validada.
            key: identificador del botón; si ya se está ejecutando, se rechaza
                (evita lanzar dos veces una macro por un doble toque).
        """
        if key is not None:
            if key in self._running:
                return ActionResult.failure("La acción ya se está ejecutando")
            self._running.add(key)
        try:
            return await asyncio.wait_for(self._run(params, depth=0), timeout=MAX_RUNTIME_S)
        except TimeoutError:
            log.warning("Acción %s cancelada por tiempo (%ss)", params.type, MAX_RUNTIME_S)
            return ActionResult.failure(f"Tiempo máximo excedido ({int(MAX_RUNTIME_S)} s)")
        finally:
            if key is not None:
                self._running.discard(key)

    async def _run(self, params: ActionParams, depth: int) -> ActionResult:
        if depth > MAX_DEPTH:
            return ActionResult.failure(f"Demasiados niveles de macros anidadas (máx. {MAX_DEPTH})")
        plugin = self.registry.get(params.type)
        logger = logging.getLogger(f"phonedeck.plugins.{params.type}")

        async def nested(child: ActionParams) -> ActionResult:
            return await self._run(child, depth + 1)

        ctx = PluginContext(
            backend=self.backend,
            settings=self._settings(),
            logger=logger,
            run_nested=nested,
            depth=depth,
        )
        try:
            result = await plugin.run(params, ctx)
        except PlatformError as exc:
            logger.warning("Fallo en acción %s: %s", params.type, exc)
            return ActionResult.failure(str(exc))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error inesperado ejecutando %s", params.model_dump())
            return ActionResult.failure("Error interno al ejecutar la acción (ver log)")
        if depth == 0:
            log.info(
                "Acción %s → %s %s", params.type, "OK" if result.ok else "FALLO", result.message
            )
        return result
