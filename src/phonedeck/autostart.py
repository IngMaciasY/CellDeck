"""Iniciar PhoneDeck con Windows (clave Run de HKCU: no requiere administrador)."""

from __future__ import annotations

import contextlib
import logging
import sys

from phonedeck.paths import is_frozen

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PhoneDeck"


def is_supported() -> bool:
    """Solo con el .exe: en desarrollo no hay un ejecutable estable que registrar."""
    return sys.platform == "win32" and is_frozen()


def command() -> str:
    return f'"{sys.executable}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if sys.platform != "win32":
        raise OSError("Solo disponible en Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            log.info("Inicio con Windows activado: %s", command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, VALUE_NAME)
            log.info("Inicio con Windows desactivado")


def refresh_path() -> None:
    """Si el .exe se movió de carpeta, actualiza la ruta registrada."""
    if not (is_supported() and is_enabled()):
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        if value != command():
            set_enabled(True)
    except OSError:
        log.debug("No se pudo comprobar la clave de inicio", exc_info=True)
