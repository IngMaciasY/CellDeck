"""Frontend servido por el backend: tipos MIME, caché e integridad de archivos."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phonedeck.server import create_app
from phonedeck.state import AppState
from tests.conftest import LOCAL

WEB = Path(__file__).resolve().parents[1] / "web"


@pytest.fixture
def web_client(state: AppState) -> Iterator[TestClient]:
    with TestClient(create_app(state, web_dir=WEB), base_url=LOCAL, client=("127.0.0.1", 1)) as c:
        yield c


@pytest.mark.parametrize(
    "path,mime",
    [
        ("/", "text/html"),
        ("/js/app.js", "application/javascript"),
        ("/js/editor.js", "application/javascript"),
        ("/css/editor.css", "text/css"),
        ("/css/app.css", "text/css"),
        ("/manifest.json", "application/json"),
        ("/media/nosleep.webm", "video/webm"),
        ("/icons/app-192.png", "image/png"),
    ],
)
def test_static_mime_and_cache(web_client: TestClient, path: str, mime: str) -> None:
    res = web_client.get(path)
    assert res.status_code == 200
    # Con "nosniff", un .js servido como text/plain sería bloqueado por Chrome.
    assert res.headers["content-type"].startswith(mime)
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"] == "no-cache"


def test_api_is_not_cached(web_client: TestClient) -> None:
    assert web_client.get("/api/health").headers["cache-control"] == "no-store"


def test_index_references_existing_files() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"#:]+)"', html)
    assert refs, "index.html sin referencias"
    for ref in refs:
        assert (WEB / ref).is_file(), f"index.html referencia un archivo inexistente: {ref}"
    # Sin scripts inline: la CSP (default-src 'self') los bloquearía.
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert " onclick=" not in html


def test_service_worker_never_caches_api() -> None:
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    assert "url.pathname.indexOf('/api/') === 0" in sw and "'/ws'" in sw
    assert "searchParams.has('v')" in sw  # caché primero solo para recursos versionados


def test_lazy_editor_files_exist() -> None:
    for path in ("js/editor.js", "js/editor-forms.js", "css/editor.css"):
        assert (WEB / path).is_file(), path


def test_manifest_icons_exist() -> None:
    manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["display"] == "fullscreen"
    for icon in manifest["icons"]:
        assert (WEB / icon["src"]).is_file()


def test_default_config_icons_exist_in_frontend() -> None:
    """Cada icono usado por la config de ejemplo debe existir en web/js/icons.js."""
    icons_js = (WEB / "js" / "icons.js").read_text(encoding="utf-8")
    available = set(re.findall(r"^\s+'([a-z0-9-]+)':", icons_js, re.M))
    config_path = (
        Path(__file__).resolve().parents[1] / "src" / "phonedeck" / "config" / "default_config.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    used = {p["icon"] for p in config["pages"] if "icon" in p}
    used |= {i["icon"] for p in config["pages"] for i in p["items"] if "icon" in i}
    used.discard("app")  # especial: logotipo de la app extraído por la PC
    assert used <= available, f"Iconos sin dibujo: {sorted(used - available)}"


def test_spotify_logos_are_the_monochrome_official_ones() -> None:
    """Spotify solo admite su logo verde sobre negro o blanco puros, y sin alterarlo."""
    white = (WEB / "icons" / "spotify-logo-white.svg").read_text(encoding="utf-8")
    black = (WEB / "icons" / "spotify-logo-black.svg").read_text(encoding="utf-8")
    assert "fill:#fff" in white
    assert "#1ed760" not in (white + black).lower()
    assert "<script" not in white + black


def test_settings_actions_live_inside_the_gear_menu() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    menu = html[html.index('id="gear-menu"') : html.index("</header>")]
    for button in ("btn-edit", "btn-fullscreen", "btn-menu"):
        assert f'id="{button}"' in menu
    assert html.count('id="btn-menu"') == 1


def test_labels_are_not_hidden_globally() -> None:
    """Regresión: solo `.no-labels` puede ocultar las etiquetas de los botones."""
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*\.key-label\s*\{\s*display:\s*none", css)
    assert ".no-labels .key-label { display: none; }" in css
    assert len(re.findall(r"\.key-img\s*\{", css)) == 1
