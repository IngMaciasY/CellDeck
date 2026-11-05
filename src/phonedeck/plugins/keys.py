"""Plugin ``keys``: atajos de teclado (``ctrl+shift+esc``) o texto a escribir."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from phonedeck.platform.keymap import parse_combo
from phonedeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext


class KeysParams(ActionParams):
    type: Literal["keys"] = "keys"
    combo: str | None = Field(default=None, max_length=80, description="p. ej. ctrl+shift+esc")
    text: str | None = Field(default=None, max_length=2000, description="Texto a escribir")

    @field_validator("combo")
    @classmethod
    def _valid_combo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return parse_combo(value).text  # normaliza y valida (ValueError → error de validación)

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.combo is None) == (self.text is None):
            raise ValueError("Indica 'combo' o 'text' (exactamente uno)")
        if self.text is not None and not self.text:
            raise ValueError("El texto no puede estar vacío")
        return self


class KeysPlugin(ActionPlugin[KeysParams]):
    type = "keys"
    title = "Atajo de teclado / texto"
    description = "Pulsa una combinación de teclas o escribe un texto en la ventana activa."
    params_model = KeysParams

    async def execute(self, params: KeysParams, ctx: PluginContext) -> ActionResult:
        if params.combo is not None:
            await ctx.backend.send_combo(parse_combo(params.combo))
        elif params.text is not None:
            await ctx.backend.type_text(params.text)
        return ActionResult.success()
