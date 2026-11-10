"""Optimizaciones: suscripciones, caché HTTP, gzip, versionado, portadas y audio."""

from __future__ import annotations

import io
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from celldeck.assets import IMMUTABLE, compute_asset_version, render_html
from celldeck.server import create_app
from celldeck.services.now_playing import optimize_artwork
from celldeck.state import AppState
from tests.conftest import LOCAL, auth, local_token

WEB = Path(__file__).resolve().parents[1] / "web"
WS_URL = "ws://127.0.0.1:8765/ws"


# ----------------------------------------------------------------- suscripciones
def receive_types(ws: Any, until: str) -> list[str]:
    seen = []
    for _ in range(20):
        msg_type = ws.receive_json()["type"]
        seen.append(msg_type)
        if msg_type == until:
            return seen
    raise AssertionError(f"No llegó '{until}'")


async def test_hub_subscribers_count(state: AppState) -> None:
    hub = state.hub
    assert hub.subscribers("stats") == 0


def test_subscribe_filters_live_topics(client: TestClient, state: AppState) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert state.hub.subscribers("stats") == 1  # por defecto: todos los temas
        ws.send_json({"type": "subscribe", "topics": ["volume"]})
        ws.send_json({"type": "ping"})
        receive_types(ws, "pong")
        assert state.hub.subscribers("stats") == 0
        assert state.hub.subscribers("volume") == 1

        # "stats" ya no le llega; "volume" sí, y "config" siempre.
        # El bucle del TestClient vive en otro hilo: se usa su portal.
        client.portal.call(state.hub.broadcast, "stats", {"cpu": 1})  # type: ignore[union-attr]
        client.portal.call(state.hub.broadcast, "volume", {"level": 1, "muted": False})  # type: ignore[union-attr]
        assert ws.receive_json()["type"] == "volume"


def test_subscribe_sends_snapshot_of_new_topics(client: TestClient, state: AppState) -> None:
    client.portal.call(state.hub.broadcast, "stats", {"cpu": 7})  # type: ignore[union-attr]
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        receive_types(ws, "stats")  # snapshot inicial
        ws.send_json({"type": "subscribe", "topics": []})
        ws.send_json({"type": "subscribe", "topics": ["stats"]})
        msg = ws.receive_json()
        assert msg == {"type": "stats", "data": {"cpu": 7}}


# -------------------------------------------------------------- caché / sesión
def test_local_session_reuses_valid_token(client: TestClient) -> None:
    first = local_token(client)
    again = client.get("/api/session", headers=auth(first)).json()["token"]
    assert again == first
    fresh = client.get("/api/session", headers=auth("token.falso")).json()["token"]
    assert fresh != "token.falso"


@pytest.fixture
def web_client(state: AppState) -> Iterator[TestClient]:
    with TestClient(create_app(state, web_dir=WEB), base_url=LOCAL, client=("127.0.0.1", 1)) as c:
        yield c


def test_index_is_versioned_and_assets_immutable(web_client: TestClient) -> None:
    res = web_client.get("/")
    assert res.headers["cache-control"] == "no-cache"
    html = res.text
    version = compute_asset_version(WEB)
    assert f'data-v="{version}"' in html
    scripts = re.findall(r'src="(js/[^"]+)"', html)
    assert scripts and all(s.endswith(f"?v={version}") for s in scripts)
    asset = web_client.get("/" + scripts[0])
    assert asset.status_code == 200 and asset.headers["cache-control"] == IMMUTABLE
    # Sin versión: revalidar
    assert web_client.get("/js/app.js").headers["cache-control"] == "no-cache"


def test_editor_is_not_loaded_upfront(web_client: TestClient) -> None:
    html = web_client.get("/").text
    assert not re.search(r'<script[^>]+src="js/editor', html)
    assert not re.search(r'<link[^>]+href="css/editor', html)


def test_gzip(web_client: TestClient) -> None:
    res = web_client.get("/js/app.js", headers={"Accept-Encoding": "gzip"})
    assert res.headers.get("content-encoding") == "gzip"
    raw_size = (WEB / "js" / "app.js").stat().st_size
    assert res.num_bytes_downloaded < raw_size * 0.5  # bytes reales por la red


def test_render_html_only_versions_local_assets() -> None:
    html = '<html lang="es"><script src="js/a.js"></script><a href="https://x.com/js/b.js">'
    out = render_html(html, "abc")
    assert 'src="js/a.js?v=abc"' in out and "https://x.com/js/b.js" in out
    assert out.startswith('<html data-v="abc" ')


# --------------------------------------------------------------------- portadas
def _png(size: int) -> bytes:
    """Imagen "tipo foto" (ruido): como las portadas reales, comprime mal en PNG."""
    img = Image.frombytes("RGB", (size, size), os.urandom(size * size * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_optimize_artwork_shrinks_and_resizes() -> None:
    original = _png(600)
    data, mime = optimize_artwork(original)
    assert mime == "image/jpeg" and len(data) < len(original)
    with Image.open(io.BytesIO(data)) as img:
        assert max(img.size) <= 320


def test_optimize_artwork_keeps_invalid_data() -> None:
    assert optimize_artwork(b"no es una imagen") == (b"no es una imagen", "image/jpeg")


# ---------------------------------------------------------------- audio (Windows)
@pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")
def test_audio_endpoint_cache_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from celldeck.platform import windows

    backend = windows.WindowsBackend.__new__(windows.WindowsBackend)
    backend._endpoint_cache = None
    fetches: list[int] = []

    class Endpoint:
        def __init__(self, broken: bool) -> None:
            self.broken = broken

        def level(self) -> int:
            if self.broken:
                raise OSError("dispositivo desconectado")
            return 42

    endpoints = [Endpoint(broken=True), Endpoint(broken=False)]

    def fetch() -> Endpoint:
        fetches.append(1)
        return endpoints[len(fetches) - 1]

    monkeypatch.setattr(backend, "_fetch_endpoint", fetch)
    # El endpoint cacheado falla → se descarta y se pide uno nuevo una sola vez.
    assert backend._with_endpoint(lambda ep: ep.level()) == 42
    assert len(fetches) == 2
    # Las siguientes llamadas usan la caché (sin enumerar el dispositivo).
    for _ in range(5):
        backend._with_endpoint(lambda ep: ep.level())
    assert len(fetches) == 2
