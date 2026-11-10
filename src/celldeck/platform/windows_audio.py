"""Mezclador de volumen por aplicación con las sesiones de audio de Windows (pycaw).

Cada aplicación puede tener varias sesiones (Brave crea una por pestaña con sonido): aquí se
agrupan por ejecutable, igual que el mezclador de Windows, y un cambio se aplica a todas.

:class:`AudioMixer` guarda objetos COM: solo se debe usar desde el hilo COM del backend.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

import psutil

from celldeck.platform import windows_apps
from celldeck.platform.audio import SYSTEM_KEY, SessionRow, app_key, group_sessions
from celldeck.platform.base import AudioApp, PlatformError

log = logging.getLogger(__name__)

SESSION_EXPIRED = 2  # AudioSessionStateExpired: la app ya cerró su flujo de audio
SYSTEM_NAME = "Sonidos del sistema"
GONE_MESSAGE = "Esa aplicación ya no tiene audio"


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """Cómo se muestra un proceso en el mezclador."""

    key: str
    name: str
    path: str | None


def identify_process(pid: int) -> ProcessIdentity | None:
    """Nombre y ejecutable de un proceso; ``None`` si ya terminó."""
    try:
        process = psutil.Process(pid)
        try:
            path: str | None = process.exe() or None
        except psutil.AccessDenied:  # procesos elevados: solo se puede leer el nombre
            path = None
        exe_name = process.name()
    except psutil.Error:
        return None
    label = windows_apps.file_description(path) if path else None
    return ProcessIdentity(
        key=app_key(path or exe_name),
        name=label or PurePath(exe_name).stem.capitalize(),
        path=path,
    )


class AudioMixer:
    """Lee y cambia las sesiones del dispositivo de salida predeterminado."""

    def __init__(self) -> None:
        self._controls: dict[str, list[Any]] = {}  # clave → ISimpleAudioVolume de sus sesiones
        self._identities: dict[int, ProcessIdentity | None] = {}  # caché por PID

    def _identity(self, pid: int) -> ProcessIdentity | None:
        if pid not in self._identities:
            self._identities[pid] = identify_process(pid)
        return self._identities[pid]

    def list_apps(self) -> list[AudioApp]:
        try:
            return self._read()
        except PlatformError:
            raise
        except Exception as exc:  # COMError y compañía: sin dispositivo, servicio caído...
            self._controls = {}
            log.debug("No se pudieron leer las sesiones de audio", exc_info=True)
            raise PlatformError("No se pudo leer el audio de Windows") from exc

    def _read(self) -> list[AudioApp]:
        from pycaw.pycaw import AudioUtilities

        controls: dict[str, list[Any]] = {}
        rows: list[SessionRow] = []
        pids: set[int] = set()
        for session in AudioUtilities.GetAllSessions():
            if session.State == SESSION_EXPIRED:
                continue
            pid = session.ProcessId
            who = (
                ProcessIdentity(SYSTEM_KEY, SYSTEM_NAME, None) if pid == 0 else self._identity(pid)
            )
            if who is None:
                continue
            pids.add(pid)
            try:
                volume = session.SimpleAudioVolume
                row = SessionRow(
                    who.key,
                    who.name,
                    who.path,
                    float(volume.GetMasterVolume()),
                    bool(volume.GetMute()),
                )
            except Exception:  # la sesión murió ahora mismo: no debe vaciar toda la lista
                log.debug("Sesión de audio perdida al leerla", exc_info=True)
                continue
            controls.setdefault(who.key, []).append(volume)
            rows.append(row)
        self._controls = controls
        # Un PID que dejó de sonar se olvida: así no se confunde si Windows lo reutiliza.
        self._identities = {pid: who for pid, who in self._identities.items() if pid in pids}
        return group_sessions(rows)

    def _apply(self, key: str, change: Callable[[Any], None]) -> None:
        """Aplica ``change`` a las sesiones de ``key``; si caducaron, relee y reintenta."""
        try:
            if key in self._controls:
                for control in self._controls[key]:
                    change(control)
                return
        except Exception:
            log.debug("Sesión de audio caducada", exc_info=True)
        self.list_apps()
        if key not in self._controls:
            raise PlatformError(GONE_MESSAGE)
        try:
            for control in self._controls[key]:
                change(control)
        except Exception as exc:
            raise PlatformError(GONE_MESSAGE) from exc

    def set_level(self, key: str, level: int) -> None:
        value = max(0, min(100, level)) / 100.0
        self._apply(key, lambda control: control.SetMasterVolume(value, None))

    def set_muted(self, key: str, muted: bool) -> None:
        self._apply(key, lambda control: control.SetMute(int(muted), None))
