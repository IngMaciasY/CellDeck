"""Rutas HTTP de PhoneDeck."""

from phonedeck.api import routes_actions, routes_auth, routes_config

ROUTERS = (routes_auth.router, routes_config.router, routes_actions.router)

__all__ = ["ROUTERS"]
