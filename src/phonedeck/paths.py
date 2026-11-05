"""Rutas de datos y recursos, tanto en desarrollo como dentro del .exe (PyInstaller)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PhoneDeck"


def is_frozen() -> bool:
    """``True`` si se ejecuta empaquetado con PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Carpeta de datos del usuario (config, settings, logs, plugins).

    Windows: ``%APPDATA%\\PhoneDeck``. Se puede forzar con ``PHONEDECK_HOME``.
    """
    override = os.environ.get("PHONEDECK_HOME")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".config" / "phonedeck"


def resource_dir() -> Path:
    """Raíz de los recursos: el directorio temporal del .exe o la raíz del repositorio."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def web_dir() -> Path:
    """Carpeta con el frontend (``web/``)."""
    override = os.environ.get("PHONEDECK_WEB_DIR")
    return Path(override) if override else resource_dir() / "web"


def external_plugin_dirs() -> list[Path]:
    """Carpetas donde buscar plugins externos."""
    dirs = [app_data_dir() / "plugins"]
    if not is_frozen():
        dirs.append(resource_dir() / "plugins")
    return dirs
