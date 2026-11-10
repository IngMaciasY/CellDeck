"""Servicios en segundo plano que publican estado en vivo por WebSocket."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from celldeck.obs import obs_service
from celldeck.services.mixer import mixer_service
from celldeck.services.now_playing import now_playing_service
from celldeck.services.pomodoro import pomodoro_service
from celldeck.services.stats import stats_service
from celldeck.services.volume import volume_service
from celldeck.spotify import spotify_service

if TYPE_CHECKING:
    from celldeck.state import AppState

BACKGROUND_SERVICES: tuple[Callable[[AppState], Coroutine[Any, Any, None]], ...] = (
    now_playing_service,
    volume_service,
    mixer_service,
    stats_service,
    pomodoro_service,
    obs_service,
    spotify_service,
)
