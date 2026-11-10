"""Plugin ``launch``: abre programas, documentos o carpetas.

Se usa ``ShellExecute`` con la ruta y los argumentos guardados en la config: nunca se
invoca un intérprete de comandos (no hay ``shell=True``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from celldeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext

_FORBIDDEN_CHARS = ("\x00", "\n", "\r")


def _check_text(value: str) -> str:
    if any(c in value for c in _FORBIDDEN_CHARS):
        raise ValueError("Contiene caracteres de control no permitidos")
    return value


class LaunchParams(ActionParams):
    type: Literal["launch"] = "launch"
    path: str = Field(min_length=1, max_length=1024, description="Programa, documento o carpeta")
    args: list[str] = Field(default_factory=list, max_length=32)
    cwd: str | None = Field(default=None, max_length=1024)

    @field_validator("path", "cwd")
    @classmethod
    def _valid_path(cls, value: str | None) -> str | None:
        return None if value is None else _check_text(value.strip())

    @field_validator("args")
    @classmethod
    def _valid_args(cls, value: list[str]) -> list[str]:
        for arg in value:
            if len(arg) > 1024:
                raise ValueError("Argumento demasiado largo (máx. 1024)")
            _check_text(arg)
        return value


class LaunchPlugin(ActionPlugin[LaunchParams]):
    type = "launch"
    title = "Abrir programa o carpeta"
    description = "Abre un .exe, un acceso directo, un documento o una carpeta. Admite %VARIABLES%."
    params_model = LaunchParams

    async def execute(self, params: LaunchParams, ctx: PluginContext) -> ActionResult:
        await ctx.backend.open_path(params.path, params.args, params.cwd)
        return ActionResult.success()
