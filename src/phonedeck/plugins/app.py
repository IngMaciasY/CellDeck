"""Plugin ``app``: abre una aplicación instalada (Steam, Epic Games, Visual Studio, Brave...).

A diferencia de ``launch`` (ruta fija), aquí la config solo guarda el identificador de
la app y la PC la busca donde Windows la tenga registrada (ver ``phonedeck.apps``). Así
el mismo botón funciona aunque Steam esté en ``D:\\APPS`` o Visual Studio sea 2022 o 2026.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from phonedeck.apps import APPS
from phonedeck.platform.base import PlatformError
from phonedeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext


class AppParams(ActionParams):
    type: Literal["app"] = "app"
    app: str = Field(pattern=r"^[a-z0-9_-]{1,40}$", description="Aplicación del catálogo")

    @field_validator("app")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in APPS:
            raise ValueError(
                f"Aplicación desconocida: '{value}'. Disponibles: {', '.join(sorted(APPS))}"
            )
        return value


class AppPlugin(ActionPlugin[AppParams]):
    type = "app"
    title = "Abrir aplicación instalada"
    description = "Abre Steam, Epic Games, Visual Studio, Brave... estén donde estén instaladas."
    params_model = AppParams

    async def execute(self, params: AppParams, ctx: PluginContext) -> ActionResult:
        spec = APPS[params.app]
        location = await ctx.backend.find_app(params.app)
        if location is None:
            return ActionResult.failure(f"No se encontró {spec.name} instalado en esta PC")
        if location.path:
            try:
                await ctx.backend.open_path(location.path)
            except PlatformError:
                # La ruta cacheada pudo dejar de existir (app movida/actualizada): buscar de nuevo.
                ctx.backend.forget_app(params.app)
                fresh = await ctx.backend.find_app(params.app)
                if fresh is None or fresh.path in (None, location.path):
                    if fresh is not None and fresh.uri:
                        await ctx.backend.open_uri(fresh.uri)
                        return ActionResult.success()
                    raise
                await ctx.backend.open_path(fresh.path)
        elif location.uri:
            await ctx.backend.open_uri(location.uri)
        return ActionResult.success()
