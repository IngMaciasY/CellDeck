"""Servicios en segundo plano que publican estado en vivo por WebSocket."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from phonedeck.obs import obs_service
from phonedeck.services.mixer import mixer_service
from phonedeck.services.now_playing import now_playing_service
from phonedeck.services.pomodoro import pomodoro_service
from phonedeck.services.stats import stats_service
from phonedeck.services.volume import volume_service
from phonedeck.spotify import spotify_service

if TYPE_CHECKING:
    from phonedeck.state import AppState

BACKGROUND_SERVICES: tuple[Callable[[AppState], Coroutine[Any, Any, None]], ...] = (
    now_playing_service,
    volume_service,
    mixer_service,
    stats_service,
    pomodoro_service,
    obs_service,
    spotify_service,
)
