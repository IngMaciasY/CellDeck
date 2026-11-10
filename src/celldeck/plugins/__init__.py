"""Plugins de acciones incluidos en CellDeck."""

from __future__ import annotations

from celldeck.plugins.app import AppPlugin
from celldeck.plugins.base import (
    ActionParams,
    ActionPlugin,
    ActionResult,
    PluginContext,
    PluginRegistry,
)
from celldeck.plugins.keys import KeysPlugin
from celldeck.plugins.launch import LaunchPlugin
from celldeck.plugins.macro import MacroPlugin, WaitPlugin
from celldeck.plugins.media import MediaPlugin
from celldeck.plugins.system import SystemPlugin
from celldeck.plugins.url import UrlPlugin
from celldeck.plugins.volume import VolumePlugin

__all__ = [
    "ActionParams",
    "ActionPlugin",
    "ActionResult",
    "PluginContext",
    "PluginRegistry",
    "build_default_registry",
]

BUILTIN_PLUGINS: tuple[type[ActionPlugin[ActionParams]], ...] = (  # type: ignore[assignment]
    MediaPlugin,
    VolumePlugin,
    LaunchPlugin,
    AppPlugin,
    UrlPlugin,
    KeysPlugin,
    MacroPlugin,
    WaitPlugin,
    SystemPlugin,
)


def build_default_registry() -> PluginRegistry:
    """Registro con todos los plugins incluidos."""
    registry = PluginRegistry()
    for plugin_cls in BUILTIN_PLUGINS:
        registry.register(plugin_cls())
    return registry
