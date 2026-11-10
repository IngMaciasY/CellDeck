"""Plugin ``url``: abre URLs y URIs de aplicaciones (``spotify:``, ``steam://``...).

Solo se permiten los esquemas de ``settings.allowed_url_schemes``. Esquemas como
``file:``, ``javascript:`` o manejadores de protocolo exóticos (p. ej. ``ms-msdt:``)
quedan bloqueados salvo que el usuario los habilite explícitamente en la PC.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from celldeck.plugins.base import ActionParams, ActionPlugin, ActionResult, PluginContext

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def url_scheme(url: str) -> str:
    match = _SCHEME_RE.match(url)
    if not match:
        raise ValueError("La URL debe empezar por un esquema, p. ej. https: o spotify:")
    return match.group(1).lower()


class UrlParams(ActionParams):
    type: Literal["url"] = "url"
    url: str = Field(min_length=3, max_length=2048)

    @field_validator("url")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        value = value.strip()
        if any(ord(c) < 0x20 or c.isspace() for c in value):
            raise ValueError("La URL no puede contener espacios ni caracteres de control")
        url_scheme(value)
        return value


class UrlPlugin(ActionPlugin[UrlParams]):
    type = "url"
    title = "Abrir URL / URI"
    description = "Abre una web o una URI de aplicación (spotify:, steam://, ms-settings:...)."
    params_model = UrlParams

    async def execute(self, params: UrlParams, ctx: PluginContext) -> ActionResult:
        scheme = url_scheme(params.url)
        if scheme not in ctx.settings.allowed_url_schemes:
            return ActionResult.failure(
                f"El esquema '{scheme}:' no está permitido. Añádelo en los ajustes de la PC."
            )
        await ctx.backend.open_uri(params.url)
        return ActionResult.success()
