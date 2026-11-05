"""Plugin ``system``: bloquear, apagar pantalla, suspender, apagar, reiniciar, cerrar sesión."""

from __future__ import annotations

from typing import Literal

from phonedeck.platform.base import SystemCommand
from phonedeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext

# Comandos que cierran programas o la sesión: el servidor exige confirmación explícita.
DANGEROUS = frozenset(
    {SystemCommand.SHUTDOWN, SystemCommand.RESTART, SystemCommand.LOGOFF, SystemCommand.HIBERNATE}
)


class SystemParams(ActionParams):
    type: Literal["system"] = "system"
    command: SystemCommand


class SystemPlugin(ActionPlugin[SystemParams]):
    type = "system"
    title = "Sistema"
    description = (
        "Bloquear, apagar pantalla, suspender, hibernar, apagar, reiniciar o cerrar sesión."
    )
    params_model = SystemParams

    async def execute(self, params: SystemParams, ctx: PluginContext) -> ActionResult:
        await ctx.backend.system_command(params.command)
        return ActionResult.success()

    def requires_confirmation(self, params: SystemParams) -> bool:
        return params.command in DANGEROUS
