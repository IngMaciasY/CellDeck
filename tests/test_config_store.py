"""Persistencia, copias de seguridad, conflictos y recarga en caliente."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from celldeck.config.models import Config
from celldeck.config.store import ConfigConflictError, ConfigStore
from celldeck.plugins import PluginRegistry


def touch_later(path: Path, text: str) -> None:
    """Escribe y fuerza un mtime distinto (algunos FS tienen resolución gruesa)."""
    path.write_text(text, encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def test_creates_default_file(tmp_path: Path, registry: PluginRegistry) -> None:
    store = ConfigStore(tmp_path / "config.json", registry)
    config = store.load()
    assert (tmp_path / "config.json").exists()
    assert config.pages[0].id == "media"
    assert store.last_error is None


def test_invalid_file_is_kept_and_reported(tmp_path: Path, registry: PluginRegistry) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    store = ConfigStore(path, registry)
    store.load()
    assert store.last_error is not None and "línea 1" in str(store.last_error)
    assert path.read_text(encoding="utf-8") == "{ esto no es json"  # no se pisa el archivo


def test_accepts_utf8_bom(tmp_path: Path, registry: PluginRegistry) -> None:
    path = tmp_path / "config.json"
    data = {"pages": [{"id": "p", "name": "Página", "items": []}]}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode())
    store = ConfigStore(path, registry)
    assert store.load().pages[0].name == "Página"


def _one_page(store: ConfigStore, name: str) -> Config:
    return store.parse({"pages": [{"id": "p", "name": name, "items": []}]})


def test_save_backup_and_conflict(tmp_path: Path, registry: PluginRegistry) -> None:
    store = ConfigStore(tmp_path / "config.json", registry)
    store.load()
    rev1 = store.revision
    rev2 = store.save(_one_page(store, "Uno"), expected_revision=rev1)
    assert rev2 != rev1
    assert len(list((tmp_path / "backups").glob("config-*.json"))) == 1
    with pytest.raises(ConfigConflictError):
        store.save(_one_page(store, "Dos"), expected_revision=rev1)
    assert json.loads((tmp_path / "config.json").read_text("utf-8"))["pages"][0]["name"] == "Uno"


def test_check_reload_detects_external_edit(tmp_path: Path, registry: PluginRegistry) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path, registry)
    store.load()
    assert store.check_reload() is False  # sin cambios

    touch_later(path, json.dumps({"pages": [{"id": "x", "name": "Externa", "items": []}]}))
    assert store.check_reload() is True
    assert store.config.pages[0].name == "Externa"

    # Un JSON roto no reemplaza la config buena
    touch_later(path, "{roto")
    assert store.check_reload() is False
    assert store.config.pages[0].name == "Externa"
    assert store.last_error is not None


async def test_watch_calls_callback(tmp_path: Path, registry: PluginRegistry) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path, registry)
    store.load()
    seen: list[str] = []

    async def on_change(config: Config) -> None:
        seen.append(config.pages[0].name)

    task = asyncio.create_task(store.watch(on_change, interval=0.01))
    touch_later(path, json.dumps({"pages": [{"id": "x", "name": "Vigilada", "items": []}]}))
    for _ in range(100):
        if seen:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    assert seen == ["Vigilada"]
