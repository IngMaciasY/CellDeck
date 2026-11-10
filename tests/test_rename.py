"""Cambio de nombre PhoneDeck → CellDeck: quien ya lo usaba conserva sus datos."""

from __future__ import annotations

from pathlib import Path

import pytest

from celldeck import paths


@pytest.fixture
def appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("CELLDECK_HOME", raising=False)
    return tmp_path


def make_legacy(appdata: Path) -> Path:
    legacy = appdata / "PhoneDeck"
    (legacy / "backups").mkdir(parents=True)
    (legacy / "config.json").write_text('{"version": 1}', encoding="utf-8")
    (legacy / "settings.json").write_text('{"pin": "123456"}', encoding="utf-8")
    return legacy


def test_copies_legacy_folder_once(appdata: Path) -> None:
    legacy = make_legacy(appdata)
    assert paths.migrate_legacy_data_dir() == legacy
    target = appdata / "CellDeck"
    assert (target / "settings.json").read_text(encoding="utf-8") == '{"pin": "123456"}'
    assert (target / "backups").is_dir()
    assert (legacy / "config.json").exists()  # se copia, no se mueve: queda de respaldo
    # Segunda vez: la carpeta nueva ya existe y no se toca.
    (target / "config.json").write_text("cambiado", encoding="utf-8")
    assert paths.migrate_legacy_data_dir() is None
    assert (target / "config.json").read_text(encoding="utf-8") == "cambiado"


def test_never_overwrites_existing_data(appdata: Path) -> None:
    make_legacy(appdata)
    (appdata / "CellDeck").mkdir()
    assert paths.migrate_legacy_data_dir() is None
    assert not (appdata / "CellDeck" / "config.json").exists()


def test_nothing_to_migrate(appdata: Path) -> None:
    assert paths.migrate_legacy_data_dir() is None
    assert not (appdata / "CellDeck").exists()


def test_custom_home_skips_migration(appdata: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_legacy(appdata)
    monkeypatch.setenv("CELLDECK_HOME", str(appdata / "otra"))
    assert paths.migrate_legacy_data_dir() is None
    assert not (appdata / "CellDeck").exists()


def test_main_uses_migrated_folder(appdata: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` copia los datos antes de abrir el log en la carpeta nueva."""
    from celldeck import __main__ as entry

    make_legacy(appdata)
    seen: dict[str, Path] = {}

    def fake_setup_logging(log_dir: Path, debug: bool = False) -> Path:
        seen["log_dir"] = log_dir
        raise SystemExit(0)

    monkeypatch.setattr(entry, "setup_logging", fake_setup_logging)
    with pytest.raises(SystemExit):
        entry.main(["--no-tray"])
    assert seen["log_dir"] == appdata / "CellDeck" / "logs"
    assert (appdata / "CellDeck" / "settings.json").exists()
