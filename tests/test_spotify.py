"""Puente con Spotify: login PKCE, tokens, playlists, portadas, reproducción y permisos."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from phonedeck import spotify as spotify_module
from phonedeck.config.settings import SettingsStore
from phonedeck.logging_setup import RedactTokensFilter
from phonedeck.platform.base import PlatformError
from phonedeck.platform.fake import FakeBackend
from phonedeck.server import create_app
from phonedeck.spotify import (
    SCOPES,
    SpotifyAuthError,
    SpotifyBridge,
    SpotifyError,
    clean_text,
    code_challenge,
    is_spotify_image,
    pick_device,
    pick_image,
    redirect_uri,
)
from phonedeck.state import AppState
from phonedeck.ws import WebSocketHub
from tests.conftest import LAN_HOST, auth, local_token
from tests.fake_spotify import JPEG, FakeSpotify, image, playlist, track
from tests.test_live import WS_URL, receive_until

CLIENT_ID = "0123456789abcdef0123456789abcdef"
LOCAL_ORIGIN = "http://127.0.0.1:8765/"


class Viewer:
    """Un celular mirando la sección de Spotify."""

    async def send_text(self, _text: str) -> None:
        return None


@pytest.fixture
def fake() -> Iterator[FakeSpotify]:
    server = FakeSpotify()
    server.start()
    yield server
    server.stop()


def make_bridge(tmp_path: Any, fake: FakeSpotify, **settings: Any) -> SpotifyBridge:
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.update(spotify_client_id=CLIENT_ID, **settings)
    return SpotifyBridge(
        WebSocketHub(),
        store,
        accounts_url=fake.url,
        api_url=fake.api_url,
        allow_image=lambda url: url.startswith(fake.url),
    )


@pytest.fixture
def bridge(tmp_path: Any, fake: FakeSpotify) -> SpotifyBridge:
    return make_bridge(tmp_path, fake, spotify_refresh_token="refresh-1")


@pytest.fixture
def linked(state: AppState, fake: FakeSpotify) -> AppState:
    """App con una cuenta vinculada contra el Spotify simulado."""
    state.settings_store.update(spotify_client_id=CLIENT_ID, spotify_refresh_token="refresh-1")
    state.spotify = SpotifyBridge(
        state.hub,
        state.settings_store,
        accounts_url=fake.url,
        api_url=fake.api_url,
        allow_image=lambda url: url.startswith(fake.url),
    )
    state.hub.set_provider("spotify", state.spotify.payload)
    return state


@contextlib.asynccontextmanager
async def running(bridge: SpotifyBridge) -> AsyncIterator[SpotifyBridge]:
    bridge.hub._clients[Viewer()] = frozenset({"spotify"})  # type: ignore[index]
    task = asyncio.create_task(bridge.run())
    try:
        yield bridge
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def until(check: Callable[[], bool], limit: float = 3.0) -> None:
    async with asyncio.timeout(limit):
        while not check():  # noqa: ASYNC110
            await asyncio.sleep(0.01)


def wait_for(check: Callable[[], bool], limit: float = 3.0) -> None:
    """Las órdenes a Spotify van en segundo plano: el resultado llega un instante después."""
    end = time.monotonic() + limit
    while not check():
        assert time.monotonic() < end, "No ocurrió a tiempo"
        time.sleep(0.01)


def login_query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def complete_authorize(fake: FakeSpotify, url: str) -> None:
    """Lo que hace la página de Spotify: guarda el reto antes de devolver el código."""
    fake.last_challenge = login_query(url)["code_challenge"]


# ------------------------------------------------------------------- funciones
def test_challenge_matches_the_rfc_7636_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_redirect_uri_uses_the_ip_because_spotify_rejects_localhost() -> None:
    assert redirect_uri(8765) == "http://127.0.0.1:8765/api/spotify/callback"


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://i.scdn.co/image/ab67", True),
        ("https://mosaic.scdn.co/640/ab67", True),
        ("https://image-cdn-ak.spotifycdn.com/image/ab67", True),
        ("http://i.scdn.co/image/ab67", False),
        ("https://i.scdn.co:8443/image/ab67", False),
        ("https://i.scdn.co.evil.com/x", False),
        ("https://evilscdn.co/x", False),
        ("https://i.scdn.co@evil.com/x", False),
        ("https://127.0.0.1/x", False),
        ("file:///c:/windows/win.ini", False),
        ("https://i.scdn.co:puerto/x", False),
    ],
)
def test_only_spotify_image_hosts_are_downloaded(url: str, allowed: bool) -> None:
    assert is_spotify_image(url) is allowed


def test_pick_image_prefers_the_smallest_that_covers_the_width() -> None:
    images = [image("grande", 640), image("media", 300), image("chica", 64)]
    assert pick_image(images, 160) == "media"
    assert pick_image(images, 64) == "chica"
    assert pick_image(images, 1000) == "grande"
    assert pick_image([{"url": "sin-medidas", "width": None}], 160) == "sin-medidas"
    assert pick_image([], 160) is None
    assert pick_image(None, 160) is None


def test_clean_text_removes_links_and_entities() -> None:
    raw = 'Lo mejor de <a href="spotify:x">Rock</a> &amp; Pop&#x27;s'
    assert clean_text(raw) == "Lo mejor de Rock & Pop's"
    assert clean_text(None) == ""


def test_pick_device_prefers_the_pc() -> None:
    devices = [
        {"id": "tv", "type": "TV"},
        {"id": "bloqueado", "type": "Computer", "is_restricted": True},
        {"id": "pc", "type": "Computer"},
    ]
    assert pick_device(devices) == "pc"
    assert pick_device([]) is None


def test_oauth_code_is_not_written_to_the_log() -> None:
    import logging

    message = 'GET /api/spotify/callback?code=AQD-secreto_1&state=abc123 HTTP/1.1"'
    record = logging.LogRecord("uvicorn", logging.INFO, "", 1, message, None, None)
    RedactTokensFilter().filter(record)
    assert "AQD-secreto" not in record.getMessage()
    assert "abc123" not in record.getMessage()


# ----------------------------------------------------------------------- login
def test_login_url_has_pkce_and_only_the_needed_scopes(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    query = login_query(bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN))
    assert query["client_id"] == CLIENT_ID
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == redirect_uri(8765)
    assert set(query["scope"].split()) == set(SCOPES)
    assert "client_secret" not in query
    pending = next(iter(bridge._logins.values()))
    assert query["code_challenge"] == code_challenge(pending.verifier)
    assert 43 <= len(pending.verifier) <= 128


def test_login_needs_a_client_id(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    bridge._store.update(spotify_client_id="")
    with pytest.raises(SpotifyError, match="Falta configurar"):
        bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)


async def test_finishing_login_stores_the_refresh_token(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    url = bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    complete_authorize(fake, url)
    result = await bridge.finish_login(login_query(url)["state"], "codigo", "")
    assert result == ("ok", LOCAL_ORIGIN)
    assert bridge._store.settings.spotify_refresh_token == "refresh-1"


async def test_login_state_works_only_once(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    url = bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    complete_authorize(fake, url)
    login_state = login_query(url)["state"]
    assert (await bridge.finish_login(login_state, "codigo", ""))[0] == "ok"
    assert await bridge.finish_login(login_state, "codigo", "") == ("error", "/")


async def test_unknown_state_is_rejected_without_calling_spotify(
    tmp_path: Any, fake: FakeSpotify
) -> None:
    bridge = make_bridge(tmp_path, fake)
    assert await bridge.finish_login("inventado", "codigo", "") == ("error", "/")
    assert fake.tokens_requested == 0
    assert not bridge._store.settings.spotify_refresh_token


async def test_expired_login_is_rejected(
    tmp_path: Any, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spotify_module, "LOGIN_TTL_S", -1.0)
    bridge = make_bridge(tmp_path, fake)
    url = bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    assert (await bridge.finish_login(login_query(url)["state"], "codigo", ""))[0] == "error"
    assert fake.tokens_requested == 0


async def test_denied_login_goes_back_to_the_app(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    url = bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    result = await bridge.finish_login(login_query(url)["state"], "", "access_denied")
    assert result == ("denied", LOCAL_ORIGIN)


async def test_wrong_verifier_does_not_link(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    url = bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    fake.last_challenge = "otro-reto"
    assert (await bridge.finish_login(login_query(url)["state"], "codigo", ""))[0] == "error"
    assert not bridge._store.settings.spotify_refresh_token


def test_pending_logins_are_bounded(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake)
    for _ in range(50):
        bridge.start_login(redirect_uri(8765), LOCAL_ORIGIN)
    assert len(bridge._logins) == spotify_module.MAX_PENDING_LOGINS


async def test_changing_client_id_forgets_the_session(bridge: SpotifyBridge) -> None:
    await bridge.save_client_id("f" * 32)
    assert bridge._store.settings.spotify_refresh_token == ""
    assert bridge.payload()["status"] == "unlinked"


async def test_saving_the_same_client_id_keeps_the_session(bridge: SpotifyBridge) -> None:
    await bridge.save_client_id(CLIENT_ID)
    assert bridge._store.settings.spotify_refresh_token == "refresh-1"


async def test_unlink_forgets_tokens_and_covers(bridge: SpotifyBridge) -> None:
    await bridge.playlists(0)
    bridge._image_urls["k"] = "url"
    await bridge.unlink()
    assert bridge._store.settings.spotify_refresh_token == ""
    assert bridge._access is None
    assert not bridge._image_urls
    assert bridge.payload() == {
        "status": "unlinked",
        "message": spotify_module.NOT_LINKED_MESSAGE,
        "user": None,
        "player": None,
        "relink": False,
    }


# ---------------------------------------------------------------------- tokens
async def test_access_token_is_renewed_only_when_needed(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.playlists(0)
    await bridge.playlists(0)
    assert fake.tokens_requested == 1


async def test_expired_access_token_is_renewed_before_the_call(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.expires_in = 30  # menos que el margen: caduca enseguida
    await bridge.playlists(0)
    before = fake.tokens_requested
    await bridge.playlists(0)
    assert fake.tokens_requested == before + 1


async def test_rotated_refresh_token_is_saved_to_disk(
    bridge: SpotifyBridge, fake: FakeSpotify, tmp_path: Any
) -> None:
    fake.rotate = True
    await bridge.playlists(0)
    assert bridge._store.settings.spotify_refresh_token == fake.refresh_token != "refresh-1"
    assert fake.refresh_token in (tmp_path / "settings.json").read_text(encoding="utf-8")


async def test_refresh_token_survives_when_spotify_does_not_rotate_it(
    bridge: SpotifyBridge,
) -> None:
    await bridge.playlists(0)
    assert bridge._store.settings.spotify_refresh_token == "refresh-1"


async def test_rejected_access_token_is_renewed_and_retried_once(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.playlists(0)
    fake.reject_access_once = True
    assert (await bridge.playlists(0))["items"]
    assert fake.tokens_requested == 2


async def test_concurrent_calls_renew_the_token_once(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.rotate = True  # dos renovaciones a la vez invalidarían el token rotado
    await asyncio.gather(*(bridge.playlists(0) for _ in range(5)))
    assert fake.tokens_requested == 1


async def test_revoked_session_needs_a_new_link(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.reject_refresh = True
    with pytest.raises(SpotifyAuthError):
        await bridge.playlists(0)
    assert bridge._store.settings.spotify_refresh_token == ""
    assert bridge.payload()["status"] == "expired"
    assert bridge.payload()["message"] == spotify_module.EXPIRED_MESSAGE


async def test_network_failure_keeps_the_session(tmp_path: Any, fake: FakeSpotify) -> None:
    bridge = make_bridge(tmp_path, fake, spotify_refresh_token="refresh-1")
    fake.stop()
    with pytest.raises(SpotifyError, match="No se pudo conectar"):
        await bridge.playlists(0)
    assert bridge._store.settings.spotify_refresh_token == "refresh-1"


async def test_tokens_never_reach_the_payload(bridge: SpotifyBridge) -> None:
    await bridge.playlists(0)
    text = str(bridge.payload())
    assert "refresh-1" not in text
    assert bridge._access is not None
    assert bridge._access not in text
    assert CLIENT_ID not in text


# ------------------------------------------------------------------- playlists
async def test_playlists_show_basic_information(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.playlists = [
        playlist(
            "propia",
            total=12,
            name="Mi lista",
            description="Rock &amp; más",
            public=False,
            images=[image(f"{fake.url}/img/a.jpg")],
        ),
        playlist("seguida", "spotify"),
        playlist("colab", "amigo", collaborative=True),
    ]
    items = (await bridge.playlists(0))["items"]
    mine = items[0]
    assert mine["name"] == "Mi lista"
    assert mine["description"] == "Rock & más"
    assert mine["total"] == 12
    assert mine["owner"] == "Demo"
    assert mine["public"] is False
    assert mine["uri"] == "spotify:playlist:propia"
    assert mine["image"]
    assert [i["readable"] for i in items] == [True, False, True]


async def test_playlists_accept_the_old_field_and_missing_counts(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.playlists = [
        playlist("vieja", total=None, tracks={"total": 7}),
        playlist("sinconteo", "spotify", total=None),
    ]
    items = (await bridge.playlists(0))["items"]
    assert [i["total"] for i in items] == [7, None]


async def test_playlists_skip_null_entries(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.playlists = [None, playlist("buena")]  # type: ignore[list-item]
    assert [i["id"] for i in (await bridge.playlists(0))["items"]] == ["buena"]


async def test_playlists_paginate(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.playlists = [playlist(f"p{i}") for i in range(75)]
    first = await bridge.playlists(0)
    assert len(first["items"]) == 50
    assert first["next_offset"] == 50
    assert first["total"] == 75
    second = await bridge.playlists(50)
    assert len(second["items"]) == 25
    assert second["next_offset"] is None


async def test_tracks_show_title_artist_and_cover(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.items["propia"] = [
        track(
            "a1",
            "Tema",
            artists=[{"name": "Uno"}, {"name": "Dos"}],
            album={"name": "Disco", "images": [image(f"{fake.url}/img/b.jpg", 64)]},
        )
    ]
    page = await bridge.playlist_tracks("propia", 0)
    assert page["available"] is True
    song = page["items"][0]
    assert song["title"] == "Tema"
    assert song["artists"] == "Uno, Dos"
    assert song["album"] == "Disco"
    assert song["uri"] == "spotify:track:a1"
    assert song["image"]


async def test_tracks_handle_local_files_episodes_and_gaps(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    episode = {
        "item": {
            "type": "episode",
            "uri": "spotify:episode:e1",
            "name": "Capítulo",
            "show": {"name": "Podcast"},
            "images": [],
        }
    }
    local = track("x", "Archivo mío", is_local=True, uri="spotify:local:Artista:::Archivo:200")
    old_shape = {"track": track("o1", "Forma vieja")["item"]}
    fake.items["propia"] = [None, {"item": None}, episode, local, old_shape]
    items = (await bridge.playlist_tracks("propia", 0))["items"]
    assert [i["title"] for i in items] == ["Capítulo", "Archivo mío", "Forma vieja"]
    assert items[0]["artists"] == "Podcast"
    assert items[1]["uri"] is None  # no se puede reproducir
    assert items[2]["uri"] == "spotify:track:o1"


async def test_followed_playlist_reports_no_content_instead_of_failing(
    bridge: SpotifyBridge,
) -> None:
    page = await bridge.playlist_tracks("seguida", 0)
    assert page == {"available": False, "items": [], "total": None, "next_offset": None}


async def test_rate_limit_stops_calls_until_retry_after(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.playlists(0)
    fake.rate_limited = 60
    with pytest.raises(SpotifyError, match="pidió esperar"):
        await bridge.playlists(0)
    calls = len(fake.calls)
    with pytest.raises(SpotifyError, match="pidió esperar"):
        await bridge.playlists(0)
    assert len(fake.calls) == calls  # ni siquiera se intenta


# -------------------------------------------------------------------- portadas
async def image_key(bridge: SpotifyBridge, fake: FakeSpotify) -> str:
    fake.playlists = [playlist("propia", images=[image(f"{fake.url}/img/a.jpg")])]
    key: str = (await bridge.playlists(0))["items"][0]["image"]
    return key


async def test_image_is_served_from_an_opaque_key(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    key = await image_key(bridge, fake)
    assert "img" not in key
    assert await bridge.image(key) == (JPEG, "image/jpeg")


async def test_unknown_image_key_downloads_nothing(bridge: SpotifyBridge) -> None:
    assert await bridge.image("0" * 32) is None


async def test_image_is_cached(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    key = await image_key(bridge, fake)
    await bridge.image(key)
    fake.image_status = 500
    assert await bridge.image(key) == (JPEG, "image/jpeg")


async def test_image_cache_is_bounded(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spotify_module, "MAX_IMAGE_CACHE_BYTES", len(JPEG) * 2)
    fake.playlists = [
        playlist(f"p{i}", images=[image(f"{fake.url}/img/{i}.jpg")]) for i in range(4)
    ]
    for item in (await bridge.playlists(0))["items"]:
        await bridge.image(item["image"])
    assert len(bridge._images) == 2
    assert bridge._image_bytes == len(JPEG) * 2


@pytest.mark.parametrize("mime", ["text/html", "image/svg+xml", "application/json"])
async def test_only_bitmap_images_are_served(
    bridge: SpotifyBridge, fake: FakeSpotify, mime: str
) -> None:
    fake.image_type = mime
    assert await bridge.image(await image_key(bridge, fake)) is None


async def test_redirects_are_not_followed(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.image_redirect = f"{fake.url}/img/otra.jpg"
    assert await bridge.image(await image_key(bridge, fake)) is None


async def test_oversized_image_is_rejected(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spotify_module, "MAX_IMAGE_BYTES", 4)
    key = await image_key(bridge, fake)
    with pytest.raises(SpotifyError):
        await bridge.image(key)


async def test_cover_outside_spotify_is_not_offered(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.playlists = [playlist("propia", images=[image("https://evil.example/a.jpg")])]
    assert (await bridge.playlists(0))["items"][0]["image"] is None


# ---------------------------------------------------------------- reproducción
@pytest.mark.parametrize(
    "action,expected",
    [
        ("play", "PUT /v1/me/player/play"),
        ("pause", "PUT /v1/me/player/pause"),
        ("next", "POST /v1/me/player/next"),
        ("previous", "POST /v1/me/player/previous"),
    ],
)
async def test_controls(
    bridge: SpotifyBridge, fake: FakeSpotify, action: Any, expected: str
) -> None:
    await bridge.control(action)
    assert fake.commands == [(expected, "", None)]


async def test_play_from_a_song_uses_the_playlist_as_context(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.play("spotify:playlist:propia", "spotify:track:a2")
    assert fake.commands[0][2] == {
        "context_uri": "spotify:playlist:propia",
        "offset": {"uri": "spotify:track:a2"},
    }


async def test_play_without_active_device_prefers_the_pc(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.active_device = False
    fake.devices = [{"id": "tel", "type": "Smartphone"}, {"id": "pc", "type": "Computer"}]
    await bridge.play("spotify:playlist:propia", None)
    assert fake.commands[0][1] == "pc"


async def test_play_without_any_device_explains_what_to_do(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.active_device = False
    with pytest.raises(SpotifyError, match="Abre Spotify en la PC"):
        await bridge.play("spotify:playlist:propia", None)


async def test_free_account_gets_a_clear_message(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.premium = False
    with pytest.raises(SpotifyError, match="Premium"):
        await bridge.control("next")


async def test_open_playlist_uses_the_app(bridge: SpotifyBridge) -> None:
    backend = FakeBackend()
    await bridge.open_in_app(backend, "spotify:playlist:abc")
    assert backend.calls == [("open_uri", ("spotify:playlist:abc",))]


async def test_open_playlist_falls_back_to_the_browser(bridge: SpotifyBridge) -> None:
    class NoApp(FakeBackend):
        async def open_uri(self, uri: str) -> None:
            if uri.startswith("spotify:"):
                raise PlatformError("sin app")
            await super().open_uri(uri)

    backend = NoApp()
    await bridge.open_in_app(backend, "spotify:playlist:abc")
    assert backend.calls == [("open_uri", ("https://open.spotify.com/playlist/abc",))]


async def test_open_playlist_is_refused_if_no_scheme_is_allowed(bridge: SpotifyBridge) -> None:
    bridge._store.update(allowed_url_schemes=["steam"])
    backend = FakeBackend()
    with pytest.raises(SpotifyError, match="no permiten"):
        await bridge.open_in_app(backend, "spotify:playlist:abc")
    assert not backend.calls


async def test_open_playlist_respects_the_allowed_schemes(bridge: SpotifyBridge) -> None:
    bridge._store.update(allowed_url_schemes=["https"])
    backend = FakeBackend()
    await bridge.open_in_app(backend, "spotify:playlist:abc")
    assert backend.calls == [("open_uri", ("https://open.spotify.com/playlist/abc",))]


async def test_commands_without_body_are_declared_as_json(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.control("pause")
    assert fake.content_types == ["application/json"]


def test_slow_spotify_does_not_block_other_controls(
    client: TestClient, linked: AppState, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    async def slow(_action: str) -> None:
        await asyncio.to_thread(release.wait, 5)

    monkeypatch.setattr(linked.spotify, "control", slow)
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.control", "action": "next"})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")  # responde sin esperar a Spotify
        release.set()


async def test_deleted_playlist_is_not_taken_for_a_missing_device(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.command_failure = (404, {"message": "Not found."})
    with pytest.raises(SpotifyError, match="no permitió"):
        await bridge.play("spotify:playlist:borrada", None)
    assert "GET /v1/me/player/devices" not in fake.calls


async def test_missing_device_is_recognised_by_its_message_too(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.command_failure = (404, {"message": "Player command failed: No active device found"})
    with pytest.raises(SpotifyError, match="Abre Spotify en la PC"):
        await bridge.control("play")
    assert "GET /v1/me/player/devices" in fake.calls


async def test_spotify_outage_is_not_reported_as_a_refusal(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.command_failure = (503, {})
    with pytest.raises(SpotifyError, match="No se pudo conectar"):
        await bridge.control("next")


async def test_command_accepts_a_text_answer(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.command_text = b"no es json"
    await bridge.control("next")
    assert len(fake.commands) == 1


async def test_commands_keep_the_order_of_the_taps(
    bridge: SpotifyBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    done: list[str] = []

    async def send(_method: str, path: str, *_rest: Any) -> None:
        await asyncio.sleep(0.05 if path.endswith("play") else 0)  # la primera tarda más
        done.append(path)

    monkeypatch.setattr(bridge, "_send_command", send)
    await asyncio.gather(bridge.control("play"), bridge.control("pause"))
    assert done == ["/me/player/play", "/me/player/pause"]


async def test_waiting_commands_are_limited(
    bridge: SpotifyBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()

    async def send(*_args: Any) -> None:
        await release.wait()

    monkeypatch.setattr(bridge, "_send_command", send)
    limit = spotify_module.MAX_QUEUED_COMMANDS
    tasks = [asyncio.create_task(bridge.control("next")) for _ in range(limit)]
    await asyncio.sleep(0)
    with pytest.raises(SpotifyError, match="espera un momento"):
        await bridge.control("next")
    release.set()
    await asyncio.gather(*tasks)
    assert bridge._queued_commands == 0


# ----------------------------------------------------------------------- bucle
def fast_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spotify_module, "POLL_S", 0.02)
    monkeypatch.setattr(spotify_module, "MAX_RETRY_S", 0.05)
    monkeypatch.setattr(spotify_module, "AFTER_COMMAND_S", 0.0)


async def test_polls_the_player_while_someone_watches(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    fake.player = {
        "is_playing": True,
        "device": {"name": "MI-PC"},
        "item": {"name": "Tema", "artists": [{"name": "Uno"}], "album": {"images": []}},
    }
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "online")
        await until(lambda: bridge.payload()["player"] is not None)
        data = bridge.payload()
    assert data["user"] == "Demo"
    assert 0 <= data["player"].pop("progress_age_ms") < 5000
    assert data["player"] == {
        "playing": True,
        "uri": None,
        "progress_ms": 0,
        "duration_ms": 0,
        "title": "Tema",
        "artists": "Uno",
        "device": "MI-PC",
        "image": None,
    }


async def test_podcast_keeps_the_player_controls(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.player = {
        "is_playing": True,
        "currently_playing_type": "episode",
        "device": {"name": "MI-PC"},
        "item": {
            "type": "episode",
            "name": "Capítulo 1",
            "show": {"name": "Mi podcast"},
            "images": [image(f"{fake.url}/img/e.jpg", 64)],
        },
    }
    await bridge._poll()
    player = bridge.payload()["player"]
    assert player["title"] == "Capítulo 1"
    assert player["artists"] == "Mi podcast"
    assert player["image"]


async def test_playback_without_item_keeps_the_player_controls(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.player = {"is_playing": True, "currently_playing_type": "ad", "item": None}
    await bridge._poll()
    assert bridge.payload()["player"]["playing"] is True


async def test_no_playback_is_not_an_error(
    bridge: SpotifyBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "online")
        assert bridge.payload()["player"] is None


async def test_nobody_watching_means_no_calls(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert fake.calls == []
    assert fake.tokens_requested == 0


async def test_unconfigured_account_makes_no_calls(
    tmp_path: Any, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    bridge = make_bridge(tmp_path, fake)
    bridge._store.update(spotify_client_id="")
    async with running(bridge):
        await asyncio.sleep(0.08)
        assert bridge.payload()["status"] == "unconfigured"
    assert fake.calls == []


async def test_session_revoked_while_watching_is_reported(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    fake.reject_refresh = True
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "expired")


async def test_account_outside_the_allowlist_is_reported(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    fake.me_status = 403
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "forbidden")
        assert "Premium" in bridge.payload()["message"]


async def test_recovers_when_spotify_comes_back(
    tmp_path: Any, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_loop(monkeypatch)
    bridge = make_bridge(tmp_path, fake, spotify_refresh_token="refresh-1")
    port = fake.port
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "online")
        fake.stop()
        bridge._access = None  # obliga a salir a la red
        await until(lambda: bridge.payload()["status"] == "offline")
        fake.start(port)
        await until(lambda: bridge.payload()["status"] == "online")


async def hold_api(bridge: SpotifyBridge, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Deja las respuestas de Spotify en espera. Devuelve (ya_llegó, soltar)."""
    arrived = asyncio.Event()
    release = asyncio.Event()
    original = bridge._api

    async def held(*args: Any) -> Any:
        data = await original(*args)
        arrived.set()
        await release.wait()
        return data

    monkeypatch.setattr(bridge, "_api", held)
    return arrived, release


async def test_unlinking_during_a_poll_leaves_nothing_on_screen(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.player = {"is_playing": True, "item": {"name": "Tema"}}
    await bridge._ensure_user()
    arrived, release = await hold_api(bridge, monkeypatch)
    poll = asyncio.create_task(bridge._poll())
    await arrived.wait()
    await bridge.unlink()
    release.set()
    await poll
    assert bridge.payload() == {
        "status": "unlinked",
        "message": spotify_module.NOT_LINKED_MESSAGE,
        "user": None,
        "player": None,
        "relink": False,
    }


async def test_answer_from_the_old_account_is_not_kept_after_a_new_link(
    bridge: SpotifyBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    arrived, release = await hold_api(bridge, monkeypatch)
    pending = asyncio.create_task(bridge._ensure_user())
    await arrived.wait()
    bridge._reset_session()  # se vinculó otra cuenta mientras tanto
    release.set()
    with pytest.raises(SpotifyError):
        await pending
    assert bridge._user_id is None


async def test_failure_from_the_old_session_is_ignored(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    await bridge._ensure_user()
    arrived, release = await hold_api(bridge, monkeypatch)
    fake.rate_limited = None
    poll = asyncio.create_task(bridge._poll())
    await arrived.wait()
    bridge._reset_session()
    bridge._status = spotify_module.SpotifyStatus.CONNECTING
    release.set()
    await poll
    assert bridge.payload()["status"] == "connecting"


async def test_expired_notice_survives_a_poll_waiting_for_the_lock(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.reject_refresh = True
    await asyncio.gather(bridge.playlists(0), bridge._poll(), return_exceptions=True)
    assert bridge.payload()["status"] == "expired"
    assert bridge._failures == 0


async def test_backoff_stays_bounded_after_days_of_failures(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.me_status = 403
    bridge._failures = 5000
    assert await bridge._poll() <= spotify_module.MAX_RETRY_S
    assert bridge.payload()["status"] == "forbidden"


async def test_command_refreshes_the_player_soon(
    bridge: SpotifyBridge, fake: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spotify_module, "AFTER_COMMAND_S", 0.0)
    async with running(bridge):
        await until(lambda: bridge.payload()["status"] == "online")
        before = fake.calls.count("GET /v1/me/player")
        await bridge.control("next")  # POLL_S real son 5 s: sin esto no se consultaría aún
        await until(lambda: fake.calls.count("GET /v1/me/player") > before)


# --------------------------------------------------------------- rutas: cuenta
def lan_client(state: AppState) -> TestClient:
    state.settings_store.update(extra_allowed_hosts=[LAN_HOST])
    state.allowed_hosts.extra = [LAN_HOST]
    url = f"http://{LAN_HOST}:8765"
    return TestClient(create_app(state), base_url=url, client=("192.168.1.50", 1))


def test_settings_show_what_to_paste_in_spotify(client: TestClient) -> None:
    h = auth(local_token(client))
    assert client.get("/api/spotify/settings").status_code == 401
    assert client.get("/api/spotify/settings", headers=h).json() == {
        "client_id": "",
        "redirect_uri": "http://127.0.0.1:8765/api/spotify/callback",
        "linked": False,
    }


def test_settings_never_return_the_token(client: TestClient, linked: AppState) -> None:
    res = client.get("/api/spotify/settings", headers=auth(local_token(client)))
    assert res.json()["linked"] is True
    assert "refresh-1" not in res.text


@pytest.mark.parametrize("client_id", ["corto", "z" * 32, "a" * 33, "../../etc/passwd", ""])
def test_client_id_is_validated(client: TestClient, client_id: str) -> None:
    body = {"client_id": client_id}
    res = client.put("/api/spotify/settings", json=body, headers=auth(local_token(client)))
    assert res.status_code == 422


def test_saves_the_client_id(client: TestClient, state: AppState) -> None:
    body = {"client_id": CLIENT_ID.upper()}
    res = client.put("/api/spotify/settings", json=body, headers=auth(local_token(client)))
    assert res.status_code == 200
    assert state.settings.spotify_client_id == CLIENT_ID


def test_login_without_client_id_is_refused(client: TestClient) -> None:
    res = client.post("/api/spotify/login", headers=auth(local_token(client)))
    assert res.status_code == 409


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/spotify/settings"),
        ("put", "/api/spotify/settings"),
        ("post", "/api/spotify/login"),
        ("post", "/api/spotify/unlink"),
    ],
)
def test_account_routes_are_rejected_from_the_network(
    state: AppState, method: str, path: str
) -> None:
    state.settings_store.update(allow_remote_edit=True)
    h = auth(state.tokens.issue("celular", 1))
    with lan_client(state) as lan:
        body = {"json": {"client_id": CLIENT_ID}} if method == "put" else {}
        assert getattr(lan, method)(path, headers=h, **body).status_code == 403
    assert state.settings.spotify_client_id == ""


def test_account_routes_require_a_token(client: TestClient) -> None:
    assert client.post("/api/spotify/login").status_code == 401
    assert client.post("/api/spotify/unlink").status_code == 401


def test_callback_is_rejected_from_the_network(state: AppState) -> None:
    with lan_client(state) as lan:
        res = lan.get("/api/spotify/callback?code=x&state=y", follow_redirects=False)
    assert res.status_code == 403


def test_full_login_through_the_routes(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    linked.settings_store.update(spotify_refresh_token="")
    res = client.post("/api/spotify/login", headers=auth(local_token(client)))
    url = res.json()["url"]
    complete_authorize(fake, url)
    query = {"code": "codigo", "state": login_query(url)["state"]}
    back = client.get("/api/spotify/callback", params=query, follow_redirects=False)
    assert back.status_code == 303
    assert back.headers["location"] == f"{LOCAL_ORIGIN}#spotify=ok"
    assert linked.settings.spotify_refresh_token == "refresh-1"


def test_forged_callback_links_nothing(client: TestClient, linked: AppState) -> None:
    linked.settings_store.update(spotify_refresh_token="")
    query = {"code": "codigo-del-atacante", "state": "inventado"}
    back = client.get("/api/spotify/callback", params=query, follow_redirects=False)
    assert back.headers["location"] == "/#spotify=error"
    assert linked.settings.spotify_refresh_token == ""


def test_unlink_through_the_route(client: TestClient, linked: AppState) -> None:
    res = client.post("/api/spotify/unlink", headers=auth(local_token(client)))
    assert res.json()["linked"] is False


# --------------------------------------------------------------- rutas: datos
def remove_widget(client: TestClient, widget: str) -> None:
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    for page in current["config"]["pages"]:
        page["items"] = [i for i in page["items"] if i.get("widget") != widget]
    assert client.put("/api/config", json=current, headers=h).status_code == 200


def test_paired_phone_on_wifi_can_read_playlists(linked: AppState) -> None:
    h = auth(linked.tokens.issue("celular", 1))
    with lan_client(linked) as lan:
        res = lan.get("/api/spotify/playlists", headers=h)
        assert res.status_code == 200
        assert [i["id"] for i in res.json()["items"]] == ["propia", "seguida"]
        tracks = lan.get("/api/spotify/playlists/propia/tracks", headers=h)
        assert [i["title"] for i in tracks.json()["items"]] == ["Canción a1", "Canción a2"]


def test_data_routes_require_a_token(client: TestClient) -> None:
    assert client.get("/api/spotify/playlists").status_code == 401
    assert client.get("/api/spotify/playlists/abc/tracks").status_code == 401
    assert client.get(f"/api/spotify/image/{'0' * 32}").status_code == 401


def test_data_routes_require_the_widget(client: TestClient, linked: AppState) -> None:
    remove_widget(client, "spotify")
    token = local_token(client)
    assert client.get("/api/spotify/playlists", headers=auth(token)).status_code == 403
    url = f"/api/spotify/image/{'0' * 32}?token={token}"
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("playlist_id", ["a%2Fb", "a.b", "..%2F..%2Fme", "a" * 63])
def test_playlist_id_is_validated(client: TestClient, playlist_id: str) -> None:
    url = f"/api/spotify/playlists/{playlist_id}/tracks"
    assert client.get(url, headers=auth(local_token(client))).status_code in (404, 422)


@pytest.mark.parametrize("offset", ["-1", "100001", "x"])
def test_offset_is_validated(client: TestClient, offset: str) -> None:
    url = f"/api/spotify/playlists?offset={offset}"
    assert client.get(url, headers=auth(local_token(client))).status_code == 422


def test_spotify_failure_does_not_log_the_phone_out(client: TestClient) -> None:
    """Un 401 en el celular significa que PhoneDeck lo expulsó: Spotify nunca debe causarlo."""
    res = client.get("/api/spotify/playlists", headers=auth(local_token(client)))
    assert res.status_code == 502
    assert res.json()["detail"] == spotify_module.NOT_LINKED_MESSAGE


def test_image_route_serves_covers(client: TestClient, linked: AppState, fake: FakeSpotify) -> None:
    fake.playlists = [playlist("propia", images=[image(f"{fake.url}/img/a.jpg")])]
    token = local_token(client)
    key = client.get("/api/spotify/playlists", headers=auth(token)).json()["items"][0]["image"]
    res = client.get(f"/api/spotify/image/{key}?token={token}")
    assert res.status_code == 200
    assert res.content == JPEG
    assert res.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/spotify/image/{'0' * 32}?token={token}").status_code == 404
    assert client.get(f"/api/spotify/image/no-es-clave?token={token}").status_code == 422


# ------------------------------------------------------------ comandos en vivo
def test_control_command_reaches_spotify(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.control", "action": "pause"})
        wait_for(lambda: bool(fake.commands))
    assert fake.commands == [("PUT /v1/me/player/pause", "", None)]


def test_play_command_reaches_spotify(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    body = {"context": "spotify:playlist:abc", "track": "spotify:track:def"}
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.play"} | body)
        wait_for(lambda: bool(fake.commands))
    assert fake.commands[0][2]["context_uri"] == "spotify:playlist:abc"


def test_open_command_opens_it_on_the_pc(client: TestClient, backend: FakeBackend) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.open", "uri": "spotify:playlist:abc"})
        wait_for(lambda: ("open_uri", ("spotify:playlist:abc",)) in backend.calls)


@pytest.mark.parametrize(
    "message",
    [
        {"type": "spotify.control", "action": "shutdown"},
        {"type": "spotify.play", "context": "https://evil.example/x"},
        {"type": "spotify.play", "context": "spotify:playlist:a b"},
        {"type": "spotify.play", "context": "spotify:playlist:abc", "track": "spotify:local:x"},
        {"type": "spotify.open", "uri": "ms-settings:display"},
        {"type": "spotify.open", "uri": "spotify:playlist:abc&calc.exe"},
        {"type": "spotify.open", "uri": "spotify:playlist:abc\n"},
    ],
)
def test_commands_validate_input(
    client: TestClient, backend: FakeBackend, message: dict[str, Any]
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json(message)
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
    assert not backend.calls


def test_commands_require_the_widget(client: TestClient, linked: AppState) -> None:
    remove_widget(client, "spotify")
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.control", "action": "next"})
        assert "no hay widget 'spotify'" in receive_until(ws, "error")["data"]["message"]


def test_spotify_error_reaches_the_phone(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    fake.premium = False
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.control", "action": "next"})
        assert "Premium" in receive_until(ws, "error")["data"]["message"]


def test_subscribing_gets_the_current_status(client: TestClient) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["spotify"]})
        assert receive_until(ws, "spotify")["data"]["status"] == "unconfigured"


def test_without_the_widget_there_is_no_live_data(client: TestClient, linked: AppState) -> None:
    remove_widget(client, "spotify")
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["spotify"]})
        ws.send_json({"type": "ping"})
        seen = []
        for _ in range(10):
            seen.append(ws.receive_json()["type"])
            if seen[-1] == "pong":
                break
        assert "spotify" not in seen
        assert linked.hub.subscribers("spotify") == 0


def test_removing_the_widget_cuts_off_a_phone_already_watching(
    client: TestClient, linked: AppState
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["spotify"]})
        receive_until(ws, "spotify")
        assert linked.hub.subscribers("spotify") == 1

        remove_widget(client, "spotify")
        assert linked.hub.subscribers("spotify") == 0  # el sondeo se detiene
        client.portal.call(linked.hub.broadcast, "spotify", {"user": "Demo"}, False)  # type: ignore[union-attr]
        ws.send_json({"type": "ping"})
        for _ in range(10):
            message = ws.receive_json()
            assert message["type"] != "spotify"
            if message["type"] == "pong":
                break


def test_new_clients_do_not_count_as_spotify_viewers(client: TestClient, state: AppState) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
        assert state.hub.subscribers("spotify") == 0


# ------------------------------------------------- biblioteca, búsqueda y cola
from tests.fake_spotify import album, simple_track  # noqa: E402


def recent_entry(track_id: str, context: str | None) -> dict[str, Any]:
    entry = {"track": track(track_id)["item"], "played_at": "2026-11-07T01:00:00Z"}
    entry["context"] = {"type": "playlist", "uri": context} if context else None
    return entry


async def test_recent_keeps_order_skips_repeats_and_knows_the_context(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.recent = [
        recent_entry("a", "spotify:playlist:mix"),
        recent_entry("b", None),
        recent_entry("a", "spotify:playlist:mix"),  # se escuchó dos veces
        recent_entry("c", "spotify:artist:xyz"),  # contexto que no se puede reproducir
    ]
    items = (await bridge.recent())["items"]
    assert [i["uri"] for i in items] == ["spotify:track:a", "spotify:track:b", "spotify:track:c"]
    assert [i["context"] for i in items] == ["spotify:playlist:mix", None, None]


async def test_liked_songs_paginate(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.liked = [{"added_at": "x", "track": track(f"t{i}")["item"]} for i in range(60)]
    first = await bridge.liked(0)
    assert len(first["items"]) == 50
    assert first["next_offset"] == 50
    assert first["items"][0]["uri"] == "spotify:track:t0"
    assert (await bridge.liked(50))["next_offset"] is None


async def test_saved_albums_and_their_songs(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.saved_albums = [
        {"added_at": "x", "album": album("disco", images=[image(f"{fake.url}/img/d.jpg")])}
    ]
    fake.album_tracks["disco"] = [simple_track("s1", "Uno"), simple_track("s2", "Dos")]
    albums = (await bridge.albums(0))["items"]
    assert albums[0] == {
        "id": "disco",
        "uri": "spotify:album:disco",
        "name": "Álbum disco",
        "artists": "Artista",
        "total": 2,
        "image": albums[0]["image"],
    }
    assert albums[0]["image"]
    page = await bridge.album_tracks("disco", 0)
    assert [t["title"] for t in page["items"]] == ["Uno", "Dos"]
    assert page["items"][0]["album_uri"] == "spotify:album:disco"  # para seguir con el álbum


async def test_missing_album_is_reported_as_unavailable(bridge: SpotifyBridge) -> None:
    assert (await bridge.album_tracks("inexistente", 0))["available"] is False


async def test_search_respects_spotifys_limit_and_skips_nulls(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.liked = [
        {"added_at": "x", "track": track(f"t{i}", f"Rock {i}")["item"]} for i in range(15)
    ]
    fake.saved_albums = [{"added_at": "x", "album": album("r", name="Rock clásico")}]
    fake.playlists = [playlist("rockp", name="Rock de los 90"), playlist("otra", name="Jazz")]
    found = await bridge.search("rock")
    assert fake.searches[0]["limit"] == "10"
    assert fake.searches[0]["type"] == "track,album,playlist"
    assert len(found["tracks"]) == 10
    assert (
        found["tracks"][0]["album_uri"] == "spotify:album:a1"
        or found["tracks"][0]["album_uri"] is None
    )
    assert [a["id"] for a in found["albums"]] == ["r"]
    assert [p["id"] for p in found["playlists"]] == ["rockp"]
    assert found["playlists"][0]["readable"] is True


async def test_search_text_is_truncated(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    await bridge.search("x" * 500)
    assert len(fake.searches[0]["q"]) == spotify_module.MAX_QUERY


async def test_queue_shows_whats_next(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    fake.queue = [track(f"q{i}")["item"] for i in range(30)]
    items = (await bridge.queue())["items"]
    assert len(items) == spotify_module.QUEUE_LIMIT
    assert items[0]["uri"] == "spotify:track:q0"


@pytest.mark.parametrize(
    "method,path",
    [
        ("recent", "/v1/me/player/recently-played"),
        ("liked", "/v1/me/tracks"),
        ("albums", "/v1/me/albums"),
    ],
)
async def test_section_without_permission_asks_to_relink(
    bridge: SpotifyBridge, fake: FakeSpotify, method: str, path: str
) -> None:
    fake.denied.add(path)
    call = getattr(bridge, method)
    with pytest.raises(SpotifyError, match="vuelve a vincular"):
        await (call() if method == "recent" else call(0))


async def test_old_link_without_the_new_permissions_is_flagged(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.granted_scope = " ".join(SCOPES[:4])  # vinculada con la versión anterior
    await bridge._poll()
    assert bridge.payload()["relink"] is True
    fake.granted_scope = " ".join(SCOPES)
    fake.access_token = "nuevo"
    bridge._access = None
    await bridge._poll()
    assert bridge.payload()["relink"] is False


async def test_unknown_permissions_are_not_flagged(bridge: SpotifyBridge) -> None:
    await bridge._poll()  # Spotify no informó los permisos
    assert bridge.payload()["relink"] is False


async def test_play_liked_songs_continues_with_the_following_ones(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    uris = [f"spotify:track:t{i}" for i in range(80)]
    await bridge.play(None, None, uris)
    assert fake.commands[0][2] == {"uris": uris[: spotify_module.MAX_PLAY_URIS]}


async def test_play_from_an_album(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    await bridge.play("spotify:album:disco", "spotify:track:s2")
    assert fake.commands[0][2] == {
        "context_uri": "spotify:album:disco",
        "offset": {"uri": "spotify:track:s2"},
    }


async def test_play_a_single_song(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    await bridge.play(None, "spotify:track:solo")
    assert fake.commands[0][2] == {"uris": ["spotify:track:solo"]}


async def test_add_to_queue(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    await bridge.add_to_queue("spotify:track:x")
    assert fake.commands[0][0] == "POST /v1/me/player/queue"
    assert fake.command_queries[0] == {"uri": "spotify:track:x"}


async def test_seek_moves_within_the_song_and_updates_at_once(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    bridge._player = {"progress_ms": 1000, "duration_ms": 200000}
    await bridge.seek(90500)
    assert fake.commands[0][0] == "PUT /v1/me/player/seek"
    assert fake.command_queries[0] == {"position_ms": "90500"}
    assert bridge._player["progress_ms"] == 90500


async def test_queue_without_active_device_keeps_the_song(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.active_device = False
    fake.devices = [{"id": "pc", "type": "Computer"}]
    await bridge.add_to_queue("spotify:track:x")
    assert fake.command_queries[0] == {"uri": "spotify:track:x", "device_id": "pc"}


async def test_player_reports_progress_for_the_seek_bar(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    fake.player = {
        "is_playing": True,
        "progress_ms": 61000,
        "item": {"uri": "spotify:track:a", "name": "Tema", "duration_ms": 200000},
    }
    await bridge._poll()
    player = bridge.payload()["player"]
    assert player["progress_ms"] == 61000
    assert player["duration_ms"] == 200000
    assert player["uri"] == "spotify:track:a"


async def test_open_album_in_the_browser(bridge: SpotifyBridge) -> None:
    bridge._store.update(allowed_url_schemes=["https"])
    backend = FakeBackend()
    await bridge.open_in_app(backend, "spotify:album:disco")
    assert backend.calls == [("open_uri", ("https://open.spotify.com/album/disco",))]


@pytest.mark.parametrize(
    "path",
    [
        "/api/spotify/recent",
        "/api/spotify/liked",
        "/api/spotify/albums",
        "/api/spotify/queue",
        "/api/spotify/albums/abc/tracks",
        "/api/spotify/search?q=rock",
    ],
)
def test_new_sections_require_token_and_widget(
    client: TestClient, linked: AppState, path: str
) -> None:
    assert client.get(path).status_code == 401
    token = local_token(client)
    assert client.get(path, headers=auth(token)).status_code == 200
    remove_widget(client, "spotify")
    assert client.get(path, headers=auth(token)).status_code == 403


@pytest.mark.parametrize("q", ["", "   ", "x" * 101])
def test_search_text_is_validated(client: TestClient, linked: AppState, q: str) -> None:
    res = client.get("/api/spotify/search", params={"q": q}, headers=auth(local_token(client)))
    assert res.status_code == 422


def test_section_without_permission_explains_it(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    fake.denied.add("/v1/me/tracks")
    res = client.get("/api/spotify/liked", headers=auth(local_token(client)))
    assert res.status_code == 502
    assert "vuelve a vincular" in res.json()["detail"]


@pytest.mark.parametrize(
    "message",
    [
        {"type": "spotify.play"},
        {"type": "spotify.play", "uris": []},
        {"type": "spotify.play", "uris": ["spotify:track:a"] * 51},
        {"type": "spotify.play", "uris": ["spotify:track:a", "spotify:local:x"]},
        {"type": "spotify.play", "context": "spotify:artist:abc"},
        {"type": "spotify.queue", "uri": "spotify:album:abc"},
        {"type": "spotify.seek", "position_ms": -1},
        {"type": "spotify.seek", "position_ms": "diez"},
        {"type": "spotify.seek", "position_ms": 10**12},
        {"type": "spotify.open", "uri": "spotify:track:abc"},
    ],
)
def test_new_commands_validate_input(
    client: TestClient, linked: AppState, fake: FakeSpotify, message: dict[str, Any]
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json(message)
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
    assert not fake.commands


def test_fifty_songs_fit_in_one_message(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    """El celular manda hasta 50 canciones: deben caber en el límite del WebSocket."""
    uris = [f"spotify:track:{'A' * 22}" for _ in range(spotify_module.MAX_PLAY_URIS)]
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.play", "uris": uris})
        wait_for(lambda: bool(fake.commands))
    assert fake.commands[0][2] == {"uris": uris}


def test_seek_and_queue_commands_reach_spotify(
    client: TestClient, linked: AppState, fake: FakeSpotify
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.seek", "position_ms": 30000})
        ws.send_json({"type": "spotify.queue", "uri": "spotify:track:x"})
        wait_for(lambda: len(fake.commands) == 2)
    assert [c[0] for c in fake.commands] == ["PUT /v1/me/player/seek", "POST /v1/me/player/queue"]


async def test_progress_says_how_old_it_is(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    """Un celular que se suscribe tarde no debe contar el tiempo desde cero."""
    fake.player = {"is_playing": True, "progress_ms": 1000, "item": {"duration_ms": 9000}}
    await bridge._poll()
    bridge._player_at -= 3.0  # la consulta fue hace 3 s
    age = bridge.payload()["player"]["progress_age_ms"]
    assert 3000 <= age < 4000


async def test_skip_to_a_song_in_the_queue_keeps_the_rest(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    await bridge.skip(3)
    assert [c[0] for c in fake.commands] == ["POST /v1/me/player/next"] * 3


async def test_skip_is_bounded(bridge: SpotifyBridge, fake: FakeSpotify) -> None:
    await bridge.skip(500)
    assert len(fake.commands) == spotify_module.QUEUE_LIMIT


async def test_forbidden_section_with_the_permission_is_not_a_relink(
    bridge: SpotifyBridge, fake: FakeSpotify
) -> None:
    """Con el permiso concedido, un 403 es otra cosa (cuenta fuera de la lista)."""
    fake.granted_scope = " ".join(SCOPES)
    fake.denied.add("/v1/me/tracks")
    await bridge._poll()
    with pytest.raises(SpotifyError) as error:
        await bridge.liked(0)
    assert "vuelve a vincular" not in str(error.value)
    assert str(error.value) == spotify_module.FORBIDDEN_MESSAGE


@pytest.mark.parametrize("count", [0, 21, -1])
def test_skip_count_is_validated(
    client: TestClient, linked: AppState, fake: FakeSpotify, count: int
) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "spotify.skip", "count": count})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
    assert not fake.commands


def test_every_spotify_command_runs_apart(client: TestClient) -> None:
    """Todas las órdenes de Spotify deben ir en segundo plano para no bloquear el volumen."""
    from phonedeck import live

    spotify_commands = [m for t, (m, _) in live.COMMANDS.items() if t.startswith("spotify.")]
    assert spotify_commands
    assert all(issubclass(m, live._SpotifyMsg) for m in spotify_commands)
