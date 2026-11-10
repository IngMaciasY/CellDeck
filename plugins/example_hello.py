"""Plugin externo de ejemplo para CellDeck.

Copia este archivo a ``%APPDATA%\\CellDeck\\plugins\\`` (o déjalo aquí en modo
desarrollo) y usa en ``config.json`` una acción así::

    {"type": "hello", "name": "Mundo"}

El celular mostrará "¡Hola, Mundo!" como notificación.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from celldeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext


class HelloParams(ActionParams):
    type: Literal["hello"] = "hello"
    name: str = Field(default="Mundo", max_length=40)


class HelloPlugin(ActionPlugin[HelloParams]):
    type = "hello"
    title = "Saludo (ejemplo)"
    description = "Plugin de ejemplo: devuelve un saludo, sin tocar el sistema."
    params_model = HelloParams

    async def execute(self, params: HelloParams, ctx: PluginContext) -> ActionResult:
        ctx.logger.info("Saludando a %s", params.name)
        return ActionResult.success(f"¡Hola, {params.name}!")


# Obligatorio: lista de instancias que CellDeck registrará.
PLUGINS = [HelloPlugin()]
