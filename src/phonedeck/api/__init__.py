"""Rutas HTTP de PhoneDeck."""

from phonedeck.api import routes_actions, routes_auth, routes_config, routes_media

ROUTERS = (routes_auth.router, routes_config.router, routes_actions.router, routes_media.router)

__all__ = ["ROUTERS"]
