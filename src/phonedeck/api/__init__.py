"""Rutas HTTP de PhoneDeck."""

from phonedeck.api import (
    routes_actions,
    routes_apps,
    routes_auth,
    routes_config,
    routes_media,
    routes_pairing,
)

ROUTERS = (
    routes_auth.router,
    routes_config.router,
    routes_actions.router,
    routes_media.router,
    routes_pairing.router,
    routes_apps.router,
)

__all__ = ["ROUTERS"]
