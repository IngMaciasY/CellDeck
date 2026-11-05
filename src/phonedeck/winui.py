"""Pequeñas utilidades de interfaz nativa: cuadros de mensaje e instancia única.

En otros sistemas (desarrollo/CI) degradan a escribir en el log.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

MB_OK = 0x0
MB_YESNO = 0x4
MB_ICONERROR = 0x10
MB_ICONWARNING = 0x30
MB_ICONINFO = 0x40
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000
IDYES = 6
ERROR_ALREADY_EXISTS = 183

_mutex: Any = None  # se mantiene vivo durante toda la ejecución


def _message_box(text: str, title: str, flags: int) -> int:
    if sys.platform != "win32":
        log.warning("[%s] %s", title, text)
        return 0
    import ctypes

    result: int = ctypes.windll.user32.MessageBoxW(
        None, text, title, flags | MB_SETFOREGROUND | MB_TOPMOST
    )
    return result


def info(text: str, title: str = "PhoneDeck") -> None:
    _message_box(text, title, MB_OK | MB_ICONINFO)


def error(text: str, title: str = "PhoneDeck") -> None:
    _message_box(text, title, MB_OK | MB_ICONERROR)


def ask(text: str, title: str = "PhoneDeck", warning: bool = False) -> bool:
    """Pregunta Sí/No. Fuera de Windows devuelve False (opción segura)."""
    flags = MB_YESNO | (MB_ICONWARNING if warning else MB_ICONINFO)
    return _message_box(text, title, flags) == IDYES


def acquire_single_instance(name: str = "Local\\PhoneDeck") -> bool:
    """Crea un mutex con nombre. ``False`` si otra instancia ya lo tiene."""
    global _mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _mutex = handle
    return True
