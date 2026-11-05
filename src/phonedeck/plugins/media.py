"""Plugin ``media``: teclas multimedia de Windows (funciona con Spotify y cualquier reproductor)."""

from __future__ import annotations

from typing import Literal

from phonedeck.platform.base import MediaKey
from phonedeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext


class MediaParams(ActionParams):
    type: Literal["media"] = "media"
    command: MediaKey


class MediaPlugin(ActionPlugin[MediaParams]):
    type = "media"
    title = "Multimedia"
    description = (
        "Play/pausa, siguiente, anterior, stop, volumen y silencio mediante teclas multimedia."
    )
    params_model = MediaParams

    async def execute(self, params: MediaParams, ctx: PluginContext) -> ActionResult:
        await ctx.backend.send_media_key(params.command)
        return ActionResult.success()
