"""Plugins ``macro`` y ``wait``: secuencias de acciones con esperas.

Ejemplo (abrir OBS y empezar a grabar)::

    {"type": "macro", "steps": [
        {"type": "launch", "path": "%ProgramFiles%\\\\obs-studio\\\\bin\\\\64bit\\\\obs64.exe"},
        {"type": "wait", "ms": 3000},
        {"type": "keys", "combo": "ctrl+shift+r"}
    ]}
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field, SerializeAsAny, ValidationInfo, field_validator

from celldeck.plugins.base import (
    ActionParams,
    ActionPlugin,
    ActionResult,
    PluginContext,
    validate_action_value,
)

MAX_STEPS = 50
MAX_WAIT_MS = 60_000


class WaitParams(ActionParams):
    type: Literal["wait"] = "wait"
    ms: int = Field(ge=0, le=MAX_WAIT_MS)


class WaitPlugin(ActionPlugin[WaitParams]):
    type = "wait"
    title = "Esperar"
    description = "Pausa (en milisegundos). Útil dentro de macros."
    params_model = WaitParams

    async def execute(self, params: WaitParams, ctx: PluginContext) -> ActionResult:
        await asyncio.sleep(params.ms / 1000)
        return ActionResult.success()


class MacroParams(ActionParams):
    type: Literal["macro"] = "macro"
    steps: Annotated[list[SerializeAsAny[ActionParams]], Field(min_length=1, max_length=MAX_STEPS)]
    stop_on_error: bool = True

    def children(self) -> list[ActionParams]:
        return list(self.steps)

    @field_validator("steps", mode="before")
    @classmethod
    def _validate_steps(cls, value: Any, info: ValidationInfo) -> list[ActionParams]:
        if not isinstance(value, list):
            raise ValueError("'steps' debe ser una lista")
        return [validate_action_value(step, info) for step in value]


class MacroPlugin(ActionPlugin[MacroParams]):
    type = "macro"
    title = "Macro"
    description = "Ejecuta varias acciones en orden, con esperas entre ellas."
    params_model = MacroParams

    async def execute(self, params: MacroParams, ctx: PluginContext) -> ActionResult:
        failures: list[str] = []
        for index, step in enumerate(params.steps, start=1):
            result = await ctx.run_nested(step)
            if not result.ok:
                msg = f"Paso {index} ({step.type}): {result.message}"
                if params.stop_on_error:
                    return ActionResult.failure(msg)
                failures.append(msg)
        if failures:
            return ActionResult.failure(" | ".join(failures))
        return ActionResult.success()
