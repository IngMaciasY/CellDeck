"""Plugins de acciones incluidos en PhoneDeck."""

from __future__ import annotations

from phonedeck.plugins.base import (
    ActionParams,
    ActionPlugin,
    ActionResult,
    PluginContext,
    PluginRegistry,
)
from phonedeck.plugins.keys import KeysPlugin
from phonedeck.plugins.launch import LaunchPlugin
from phonedeck.plugins.macro import MacroPlugin, WaitPlugin
from phonedeck.plugins.media import MediaPlugin
from phonedeck.plugins.system import SystemPlugin
from phonedeck.plugins.url import UrlPlugin
from phonedeck.plugins.volume import VolumePlugin

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
