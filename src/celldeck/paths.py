"""Rutas de datos y recursos, tanto en desarrollo como dentro del .exe (PyInstaller)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "CellDeck"
# Nombre anterior del proyecto: su carpeta de datos se copia la primera vez (ver abajo).
LEGACY_APP_NAME = "PhoneDeck"


def is_frozen() -> bool:
    """``True`` si se ejecuta empaquetado con PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Carpeta de datos del usuario (config, settings, logs, plugins).

    Windows: ``%APPDATA%\\CellDeck``. Se puede forzar con ``CELLDECK_HOME``.
    """
    override = os.environ.get("CELLDECK_HOME")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".config" / "celldeck"


def migrate_legacy_data_dir() -> Path | None:
    """Copia ``%APPDATA%\\PhoneDeck`` a ``%APPDATA%\\CellDeck`` si aún no existe la nueva.

    Así quien usaba PhoneDeck conserva botones, PIN, dispositivos emparejados y la cuenta de
    Spotify. Se copia (no se mueve) para que la carpeta antigua quede como respaldo. Devuelve la
    carpeta de origen si copió algo. No hace nada con ``CELLDECK_HOME`` ni fuera de Windows.
    """
    appdata = os.environ.get("APPDATA")
    if os.environ.get("CELLDECK_HOME") or not appdata:
        return None
    legacy = Path(appdata) / LEGACY_APP_NAME
    target = Path(appdata) / APP_NAME
    if target.exists() or not legacy.is_dir():
        return None
    shutil.copytree(legacy, target)
    return legacy


def resource_dir() -> Path:
    """Raíz de los recursos: el directorio temporal del .exe o la raíz del repositorio."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def web_dir() -> Path:
    """Carpeta con el frontend (``web/``)."""
    override = os.environ.get("CELLDECK_WEB_DIR")
    return Path(override) if override else resource_dir() / "web"


def external_plugin_dirs() -> list[Path]:
    """Carpetas donde buscar plugins externos."""
    dirs = [app_data_dir() / "plugins"]
    if not is_frozen():
        dirs.append(resource_dir() / "plugins")
    return dirs
