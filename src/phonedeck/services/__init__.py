"""Servicios en segundo plano que publican estado en vivo por WebSocket.

En el hito (c) se añaden: ahora suena, volumen y CPU/RAM.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phonedeck.state import AppState

BACKGROUND_SERVICES: tuple[Callable[[AppState], Coroutine[Any, Any, None]], ...] = ()
