"""Servicios en vivo (ahora suena, volumen, stats) con el backend simulado."""

from __future__ import annotations

from typing import Any

import pytest

from phonedeck.platform.base import MediaInfo, MediaKey, VolumeState
from phonedeck.platform.fake import FakeBackend
from phonedeck.services.base import Poller
from phonedeck.services.now_playing import (
    NowPlayingService,
    friendly_app_name,
    media_payload,
    sniff_image_mime,
)
from phonedeck.services.stats import StatsService
from phonedeck.services.volume import VolumeService
from phonedeck.state import AppState

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def spy_broadcasts(state: AppState) -> list[tuple[str, Any]]:
    """Sustituye hub.broadcast para registrar los mensajes (y mantener el snapshot)."""
    sent: list[tuple[str, Any]] = []
    original = state.hub.broadcast

    async def spy(msg_type: str, data: Any, cache: bool = True) -> None:
        sent.append((msg_type, data))
        await original(msg_type, data, cache)

    state.hub.broadcast = spy  # type: ignore[method-assign]
    return sent


def track(**kw: Any) -> MediaInfo:
    base: dict[str, Any] = {
        "title": "Peligro",
        "artist": "Reik",
        "app_id": "Spotify.exe",
        "status": "playing",
        "position_s": 10.0,
        "duration_s": 221.4,
    }
    base.update(kw)
    return MediaInfo(**base)


@pytest.mark.parametrize(
    "app_id,expected",
    [
        ("Spotify.exe", "Spotify"),
        ("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "Spotify"),
        ("Brave", "Brave"),
        ("chrome", "Chrome"),
        ("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic", "ZuneMusic"),
        ("", ""),
    ],
)
def test_friendly_app_name(app_id: str, expected: str) -> None:
    assert friendly_app_name(app_id) == expected


def test_sniff_image_mime() -> None:
    assert sniff_image_mime(PNG) == "image/png"
    assert sniff_image_mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert sniff_image_mime(b"RIFF1234WEBPVP8 ") == "image/webp"


def test_media_payload() -> None:
    assert media_payload(None) is None
    assert media_payload(track(title="", artist="")) is None
    payload = media_payload(track(artwork=PNG, artwork_hash="abc"))
    assert payload == {
        "title": "Peligro",
        "artist": "Reik",
        "album": "",
        "app": "Spotify",
        "status": "playing",
        "position": 10.0,
        "duration": 221.4,
        "artwork": "/api/media/artwork?h=abc",
    }


async def test_now_playing_only_broadcasts_changes(state: AppState, backend: FakeBackend) -> None:
    sent = spy_broadcasts(state)
    service = NowPlayingService(state)

    await service.tick()  # primera lectura: siempre se envía (aunque sea "nada")
    assert sent == [("media", None)]

    backend.now_playing = track(artwork=PNG, artwork_hash="h1")
    await service.tick()
    await service.tick()  # sin cambios → no se reenvía
    assert [m[0] for m in sent] == ["media", "media"]
    assert sent[1][1]["title"] == "Peligro"
    assert state.live.artwork is not None and state.live.artwork.mime == "image/png"

    backend.now_playing = track(status="paused", artwork=PNG, artwork_hash="h1")
    await service.tick()
    assert sent[-1][1]["status"] == "paused"

    backend.now_playing = track(status="paused", position_s=120.0, artwork=PNG, artwork_hash="h1")
    await service.tick()  # salto de posición (el usuario buscó) → se reenvía
    assert sent[-1][1]["position"] == 120.0

    backend.now_playing = None
    await service.tick()
    assert sent[-1] == ("media", None)
    assert state.live.artwork is None


async def test_volume_service(state: AppState, backend: FakeBackend) -> None:
    sent = spy_broadcasts(state)
    service = VolumeService(state)
    await service.tick()
    await service.tick()
    backend.volume = VolumeState(level=70, muted=True)
    await service.tick()
    assert sent == [
        ("volume", {"level": 50, "muted": False}),
        ("volume", {"level": 70, "muted": True}),
    ]


async def test_stats_service(state: AppState) -> None:
    await StatsService(state).tick()
    stats = state.hub.snapshot()["stats"]
    assert 0 <= stats["cpu"] <= 100
    assert 0 < stats["ram"] <= 100
    assert 0 < stats["ram_used"] <= stats["ram_total"]


async def test_poller_backoff(state: AppState) -> None:
    class Broken(Poller):
        name = "roto"
        topic = "stats"

        async def tick(self) -> None:
            raise RuntimeError("fallo")

    poller = Broken(state)
    assert not poller.wanted()  # nadie suscrito a "stats": no se consulta a Windows
    assert poller.next_delay() == Broken.idle_interval
    poller.errors = 3
    assert poller.next_delay() == min(30.0, Broken.idle_interval * 8)


async def test_fake_demo_mode_reacts_to_controls() -> None:
    demo = FakeBackend(demo=True)
    first = await demo.get_now_playing()
    assert first is not None and first.status == "playing"
    await demo.send_media_key(MediaKey.PLAY_PAUSE)
    paused = await demo.get_now_playing()
    assert paused is not None and paused.status == "paused"
    await demo.send_media_key(MediaKey.NEXT)
    nxt = await demo.get_now_playing()
    assert nxt is not None and nxt.title != first.title
