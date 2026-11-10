"""Plugin ``volume``: control preciso del volumen maestro (pycaw)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from celldeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext


class VolumeParams(ActionParams):
    type: Literal["volume"] = "volume"
    op: Literal["set", "step", "mute", "unmute", "toggle_mute"]
    value: int = Field(default=0, ge=-100, le=100)

    @model_validator(mode="after")
    def _check_value(self) -> Self:
        if self.op == "set" and not 0 <= self.value <= 100:
            raise ValueError("Para 'set' el valor debe estar entre 0 y 100")
        if self.op == "step" and self.value == 0:
            raise ValueError("Para 'step' el valor no puede ser 0")
        return self


class VolumePlugin(ActionPlugin[VolumeParams]):
    type = "volume"
    title = "Volumen"
    description = "Fija, sube/baja o silencia el volumen maestro de Windows."
    params_model = VolumeParams

    async def execute(self, params: VolumeParams, ctx: PluginContext) -> ActionResult:
        backend = ctx.backend
        if params.op == "set":
            await backend.set_volume(params.value)
        elif params.op == "step":
            current = await backend.get_volume()
            await backend.set_volume(max(0, min(100, current.level + params.value)))
        elif params.op == "toggle_mute":
            current = await backend.get_volume()
            await backend.set_mute(not current.muted)
        else:
            await backend.set_mute(params.op == "mute")
        state = await backend.get_volume()
        return ActionResult.success(level=state.level, muted=state.muted)
