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


def test_service_worker_shell_exists() -> None:
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    block = re.search(r"const SHELL = \[(.*?)\];", sw, re.S)
    assert block
    for entry in re.findall(r"'([^']+)'", block.group(1)):
        if entry != "./":
            assert (WEB / entry).is_file(), f"sw.js cachea un archivo inexistente: {entry}"


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
    assert used <= available, f"Iconos sin dibujo: {sorted(used - available)}"
