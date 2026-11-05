"""Interfaz de plugins de acciones y registro.

Cada tipo de acción (``media``, ``launch``, ``keys``...) es un :class:`ActionPlugin` con:

- ``type``: identificador usado en ``config.json`` (``"action": {"type": "media", ...}``).
- ``params_model``: modelo pydantic que valida los parámetros de la acción.
- ``execute()``: corrutina que realiza la acción usando ``ctx.backend``.

Los plugins nunca reciben datos arbitrarios de la red: solo parámetros que ya están
guardados y validados en la configuración.
"""

from __future__ import annotations

import builtins
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError, ValidationInfo
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from phonedeck.config.settings import Settings
    from phonedeck.platform.base import PlatformBackend

log = logging.getLogger(__name__)


class ActionParams(BaseModel):
    """Base de los parámetros de toda acción. Las subclases fijan ``type`` con un Literal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str

    def children(self) -> list[ActionParams]:
        """Acciones anidadas (las macros devuelven sus pasos). Por defecto ninguna."""
        return []


P = TypeVar("P", bound=ActionParams)


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Resultado de ejecutar una acción (se envía tal cual al celular)."""

    ok: bool
    message: str = ""
    data: Mapping[str, Any] | None = None

    @classmethod
    def success(cls, message: str = "", **data: Any) -> ActionResult:
        return cls(True, message, data or None)

    @classmethod
    def failure(cls, message: str) -> ActionResult:
        return cls(False, message)


@dataclass(slots=True)
class PluginContext:
    """Lo que un plugin puede usar al ejecutarse."""

    backend: PlatformBackend
    settings: Settings
    logger: logging.Logger
    run_nested: Callable[[ActionParams], Awaitable[ActionResult]]
    depth: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class ActionPlugin(ABC, Generic[P]):
    """Clase base de todos los plugins de acción."""

    type: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str] = ""
    # builtins.type: dentro de la clase, `type` es el ClassVar de arriba.
    params_model: builtins.type[P]

    @abstractmethod
    async def execute(self, params: P, ctx: PluginContext) -> ActionResult:
        """Ejecuta la acción. Debe lanzar ``PlatformError`` para errores esperados."""

    def requires_confirmation(self, params: P) -> bool:
        """``True`` si la acción es peligrosa y la UI debe pedir confirmación."""
        return False

    # Envoltorios no genéricos para el registro (que no conoce el tipo concreto).
    async def run(self, params: ActionParams, ctx: PluginContext) -> ActionResult:
        if not isinstance(params, self.params_model):
            raise TypeError(f"Parámetros de tipo {type(params).__name__} para plugin {self.type}")
        return await self.execute(params, ctx)

    def needs_confirmation(self, params: ActionParams) -> bool:
        return isinstance(params, self.params_model) and self.requires_confirmation(params)


class PluginRegistry:
    """Registro de plugins por tipo de acción."""

    def __init__(self) -> None:
        self._plugins: dict[str, ActionPlugin[Any]] = {}

    def register(self, plugin: ActionPlugin[Any]) -> None:
        if not getattr(plugin, "type", None):
            raise ValueError(f"El plugin {plugin!r} no define 'type'")
        if plugin.type in self._plugins:
            raise ValueError(f"Ya existe un plugin para el tipo '{plugin.type}'")
        self._plugins[plugin.type] = plugin
        log.debug("Plugin registrado: %s", plugin.type)

    def get(self, action_type: str) -> ActionPlugin[Any]:
        try:
            return self._plugins[action_type]
        except KeyError:
            raise KeyError(f"Tipo de acción desconocido: '{action_type}'") from None

    def types(self) -> list[str]:
        return sorted(self._plugins)

    def __contains__(self, action_type: object) -> bool:
        return action_type in self._plugins

    def validate(self, data: Any) -> ActionParams:
        """Valida un dict de acción y devuelve el modelo del plugin correspondiente."""
        if isinstance(data, ActionParams):
            return data
        if not isinstance(data, Mapping) or not isinstance(data.get("type"), str):
            raise PydanticCustomError("action_type", "La acción debe ser un objeto con 'type'")
        action_type = data["type"]
        plugin = self._plugins.get(action_type)
        if plugin is None:
            raise PydanticCustomError(
                "action_type",
                "Tipo de acción desconocido: '{t}'. Disponibles: {available}",
                {"t": action_type, "available": ", ".join(self.types())},
            )
        try:
            params: ActionParams = plugin.params_model.model_validate(
                data, context={"registry": self}
            )
            return params
        except ValidationError as exc:
            parts = []
            for err in exc.errors():
                where = ".".join(str(p) for p in err["loc"]) or "acción"
                parts.append(f"{where}: {err['msg'].removeprefix('Value error, ')}")
            details = "; ".join(parts)
            raise PydanticCustomError(
                "action_invalid",
                "Acción '{t}' inválida: {details}",
                {"t": action_type, "details": details},
            ) from None

    def describe(self) -> list[dict[str, Any]]:
        """Metadatos y JSON Schema de cada plugin (para el editor visual)."""
        return [
            {
                "type": p.type,
                "title": p.title,
                "description": p.description,
                "schema": p.params_model.model_json_schema(),
            }
            for _, p in sorted(self._plugins.items())
        ]


def validate_action_value(value: Any, info: ValidationInfo) -> ActionParams:
    """Validador pydantic reutilizable: delega en el registro pasado por ``context``."""
    if isinstance(value, ActionParams):
        return value
    registry = (info.context or {}).get("registry")
    if not isinstance(registry, PluginRegistry):
        raise PydanticCustomError(
            "no_registry", "No hay registro de plugins para validar la acción"
        )
    return registry.validate(value)
