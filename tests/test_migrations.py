"""Migración de una sola vez: las secciones nuevas en instalaciones existentes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phonedeck.config.migrations import SECTIONS_VERSION
from phonedeck.platform.fake import FakeBackend
from phonedeck.state import AppState, build_state


def old_config(**page: Any) -> dict[str, Any]:
    first = {"id": "mio", "name": "Mi página", "items": []} | page
    return {"version": 1, "pages": [first]}


def boot(tmp_path: Path, config: dict[str, Any] | None = None) -> AppState:
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return build_state(tmp_path, backend=FakeBackend())


def ids(state: AppState) -> list[str]:
    return [p.id for p in state.config_store.config.pages]


def test_new_install_gets_sections_once(tmp_path: Path) -> None:
    state = boot(tmp_path)
    assert ids(state) == ["media", "pc", "mixer", "pomodoro", "obs"]
    assert state.settings.sections_version == SECTIONS_VERSION


def test_existing_install_keeps_its_pages_and_gets_the_sections(tmp_path: Path) -> None:
    state = boot(tmp_path, old_config())
    assert ids(state) == ["mio", "mixer", "pomodoro", "obs"]
    assert state.config_store.config.has_widget("obs")
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in saved["pages"]] == ids(state)
    assert list((tmp_path / "backups").glob("config-*.json"))  # hay copia de seguridad


def test_removed_sections_do_not_come_back(tmp_path: Path) -> None:
    state = boot(tmp_path, old_config())
    config = state.config_store.config
    config.pages = [p for p in config.pages if p.id != "obs"]
    state.config_store.save(config)

    assert ids(boot(tmp_path)) == ["mio", "mixer", "pomodoro"]


def test_section_already_on_another_page_is_not_duplicated(tmp_path: Path) -> None:
    widget = {"kind": "widget", "id": "m", "widget": "mixer", "w": 3, "h": 2}
    assert ids(boot(tmp_path, old_config(items=[widget]))) == ["mio", "pomodoro", "obs"]


def test_page_id_conflict_gets_a_new_id(tmp_path: Path) -> None:
    state = boot(tmp_path, old_config(id="obs", name="Otra cosa"))
    assert ids(state) == ["obs", "mixer", "pomodoro", "obs-2"]
    assert state.config_store.config.pages[0].name == "Otra cosa"


def test_invalid_config_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{ roto", encoding="utf-8")
    state = boot(tmp_path)
    assert state.config_store.last_error is not None
    assert (tmp_path / "config.json").read_text(encoding="utf-8") == "{ roto"
    assert state.settings.sections_version == 0  # se reintentará cuando se arregle


def test_page_limit_is_respected(tmp_path: Path) -> None:
    pages = [{"id": f"p{i}", "name": f"P{i}", "items": []} for i in range(29)]
    state = boot(tmp_path, {"version": 1, "pages": pages})
    assert len(state.config_store.config.pages) == 30
    assert state.config_store.config.has_widget("mixer")
    assert not state.config_store.config.has_widget("obs")
