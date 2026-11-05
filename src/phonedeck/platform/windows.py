"""Implementación real de ``PlatformBackend`` para Windows.

- Teclado: ``SendInput`` vía ctypes (sin dependencias, sin permisos de administrador).
- Programas/URIs: ``ShellExecuteW``.
- Volumen: pycaw (COM) en un hilo dedicado con COM inicializado.
- Ahora suena: WinRT ``GlobalSystemMediaTransportControlsSessionManager``.

Nota: Windows bloquea (UIPI) la entrada simulada hacia ventanas que se ejecutan
como administrador si PhoneDeck no lo es. Es una limitación del sistema operativo.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from phonedeck.platform.base import (
    MediaInfo,
    MediaKey,
    PlatformError,
    SystemCommand,
    VolumeState,
)
from phonedeck.platform.keymap import EXTENDED_VKS, KeyCombo, parse_combo

if sys.platform != "win32":  # pragma: no cover - solo se importa en Windows
    raise ImportError("phonedeck.platform.windows solo funciona en Windows")

import ctypes
from ctypes import wintypes

log = logging.getLogger(__name__)
T = TypeVar("T")

# ---------------------------------------------------------------- SendInput (ctypes)
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT es el miembro más grande: debe estar para que sizeof(INPUT) sea correcto.
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_powrprof = ctypes.WinDLL("powrprof", use_last_error=True)

_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_user32.MapVirtualKeyW.restype = wintypes.UINT
_user32.LockWorkStation.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.PostMessageW.restype = wintypes.BOOL
_shell32.ShellExecuteW.argtypes = (
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_int,
)
_shell32.ShellExecuteW.restype = wintypes.HINSTANCE
_powrprof.SetSuspendState.argtypes = (wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.BOOLEAN)
_powrprof.SetSuspendState.restype = wintypes.BOOLEAN

SW_SHOWNORMAL = 1
HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
CREATE_NO_WINDOW = 0x08000000

_MEDIA_VK: dict[MediaKey, int] = {
    MediaKey.PLAY_PAUSE: 0xB3,
    MediaKey.NEXT: 0xB0,
    MediaKey.PREV: 0xB1,
    MediaKey.STOP: 0xB2,
    MediaKey.VOLUME_UP: 0xAF,
    MediaKey.VOLUME_DOWN: 0xAE,
    MediaKey.MUTE: 0xAD,
}

# Códigos de error de ShellExecute (valor devuelto <= 32)
_SHELL_ERRORS = {
    0: "Sin memoria",
    2: "No se encontró el archivo",
    3: "No se encontró la ruta",
    5: "Acceso denegado",
    8: "Sin memoria",
    26: "Error de uso compartido",
    27: "Asociación de archivo incompleta",
    31: "No hay ninguna aplicación asociada",
    32: "DLL no encontrada",
}


def _key_input(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def _unicode_input(code_unit: int, up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, code_unit, flags, 0, 0)))


def _send_inputs(inputs: Sequence[INPUT]) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = _user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        err = ctypes.get_last_error()
        raise PlatformError(
            f"Windows bloqueó la pulsación (SendInput {sent}/{len(inputs)}, error {err}). "
            "¿La ventana activa se ejecuta como administrador?"
        )


def _send_vk_combo(vks: Sequence[int]) -> None:
    """Pulsa todas las teclas en orden y las suelta en orden inverso (una sola llamada)."""
    down = [_key_input(vk, up=False) for vk in vks]
    up = [_key_input(vk, up=True) for vk in reversed(vks)]
    _send_inputs(down + up)


# ------------------------------------------------------------------- hilo COM
def _com_thread_init() -> None:
    """Inicializa COM (STA) en el hilo dedicado. comtypes se importa aquí a propósito
    para que su CoInitialize implícito ocurra en este hilo y no en el del event loop."""
    import comtypes

    comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)


class WindowsBackend:
    """Backend nativo de Windows."""

    name = "windows"

    def __init__(self) -> None:
        # Un único hilo para COM/Shell: pycaw y ShellExecute no son seguros entre hilos sin COM.
        self._com = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="phonedeck-com", initializer=_com_thread_init
        )
        self._artwork_cache: tuple[str, bytes] | None = None
        self._media_manager: Any = None
        self._shutdown_exe = str(
            Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "shutdown.exe"
        )

    async def _in_com(self, fn: Callable[[], T]) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._com, fn)

    # ---------------------------------------------------------------- teclado
    async def send_media_key(self, key: MediaKey) -> None:
        _send_vk_combo([_MEDIA_VK[key]])

    async def send_combo(self, combo: KeyCombo) -> None:
        _send_vk_combo(combo.keys)

    async def type_text(self, text: str) -> None:
        data = text.replace("\r\n", "\n").encode("utf-16-le")
        units = [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]
        enter = parse_combo("enter").keys
        # Se envía en bloques pequeños con pausas para no saturar aplicaciones lentas.
        chunk: list[INPUT] = []
        for unit in units:
            if unit == 0x0A:  # salto de línea → tecla Enter real
                _send_inputs(chunk)
                chunk = []
                _send_vk_combo(enter)
                continue
            chunk += [_unicode_input(unit, False), _unicode_input(unit, True)]
            if len(chunk) >= 64:
                _send_inputs(chunk)
                chunk = []
                await asyncio.sleep(0.01)
        _send_inputs(chunk)

    # ------------------------------------------------------ programas y URIs
    async def open_path(self, path: str, args: Sequence[str] = (), cwd: str | None = None) -> None:
        def _open() -> None:
            # Se expanden %VARIABLES% y ~ en el hilo COM (expanduser puede consultar el disco).
            target = os.path.expandvars(os.path.expanduser(path))
            work_dir = os.path.expandvars(cwd) if cwd else None
            params = (
                subprocess.list2cmdline([os.path.expandvars(a) for a in args]) if args else None
            )
            self._shell_execute(target, params, work_dir)

        await self._in_com(_open)

    async def open_uri(self, uri: str) -> None:
        await self._in_com(lambda: self._shell_execute(uri, None, None))

    @staticmethod
    def _shell_execute(target: str, params: str | None, cwd: str | None) -> None:
        result = _shell32.ShellExecuteW(None, "open", target, params, cwd, SW_SHOWNORMAL)
        code = int(result or 0)
        if code <= 32:
            reason = _SHELL_ERRORS.get(code, f"código {code}")
            raise PlatformError(f"No se pudo abrir '{target}': {reason}")
        log.info("Abierto: %s %s", target, params or "")

    # ---------------------------------------------------------------- volumen
    @staticmethod
    def _endpoint() -> Any:
        """Obtiene IAudioEndpointVolume del dispositivo de salida por defecto.
        Se pide en cada llamada porque el dispositivo puede cambiar (auriculares, HDMI...)."""
        from pycaw.pycaw import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if speakers is None:
            raise PlatformError("No hay dispositivo de audio de salida")
        endpoint = getattr(speakers, "EndpointVolume", None)
        if endpoint is not None:  # pycaw >= 2024
            return endpoint
        # API antigua de pycaw
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume

        iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))

    async def get_volume(self) -> VolumeState:
        def _get() -> VolumeState:
            ep = self._endpoint()
            return VolumeState(
                level=round(ep.GetMasterVolumeLevelScalar() * 100), muted=bool(ep.GetMute())
            )

        return await self._in_com(_get)

    async def set_volume(self, level: int) -> None:
        value = max(0, min(100, level)) / 100.0
        await self._in_com(lambda: self._endpoint().SetMasterVolumeLevelScalar(value, None))

    async def set_mute(self, muted: bool) -> None:
        await self._in_com(lambda: self._endpoint().SetMute(int(muted), None))

    # ------------------------------------------------------------ ahora suena
    async def get_now_playing(self) -> MediaInfo | None:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )

        if self._media_manager is None:
            self._media_manager = await SessionManager.request_async()
        session = self._media_manager.get_current_session()
        if session is None:
            return None

        props = await session.try_get_media_properties_async()
        status_code = int(session.get_playback_info().playback_status)
        status = {4: "playing", 5: "paused", 3: "stopped", 2: "stopped"}.get(status_code, "unknown")

        position = duration = None
        try:
            timeline = session.get_timeline_properties()
            duration = timeline.end_time.total_seconds() or None
            position = timeline.position.total_seconds() if duration else None
        except Exception:  # algunos reproductores no informan la línea de tiempo
            log.debug("Sin timeline para la sesión actual", exc_info=True)

        title = props.title or ""
        artist = props.artist or ""
        artwork, artwork_hash = await self._read_artwork(
            props, f"{title}|{artist}|{props.album_title}"
        )
        return MediaInfo(
            title=title,
            artist=artist,
            album=props.album_title or "",
            app_id=session.source_app_user_model_id or "",
            status=status,
            position_s=position,
            duration_s=duration,
            artwork=artwork,
            artwork_hash=artwork_hash,
        )

    async def _read_artwork(self, props: Any, key: str) -> tuple[bytes | None, str | None]:
        """Lee la portada; se cachea por pista para no releerla en cada sondeo."""
        if self._artwork_cache and self._artwork_cache[0] == key:
            data = self._artwork_cache[1]
            return data, hashlib.sha1(data, usedforsecurity=False).hexdigest()[:12]
        thumb = props.thumbnail
        if thumb is None:
            return None, None
        try:
            from winrt.windows.storage.streams import Buffer, InputStreamOptions

            stream = await thumb.open_read_async()
            size = int(stream.size)
            if size <= 0 or size > 5 * 1024 * 1024:
                return None, None
            buf = Buffer(size)
            await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            data = bytes(memoryview(buf)[: buf.length])
        except Exception:
            log.debug("No se pudo leer la portada", exc_info=True)
            return None, None
        self._artwork_cache = (key, data)
        return data, hashlib.sha1(data, usedforsecurity=False).hexdigest()[:12]

    # ---------------------------------------------------------------- sistema
    async def system_command(self, command: SystemCommand) -> None:
        if command is SystemCommand.LOCK:
            if not _user32.LockWorkStation():
                raise PlatformError("No se pudo bloquear la sesión")
        elif command is SystemCommand.MONITOR_OFF:
            # PostMessage (no SendMessage) para no quedarnos bloqueados esperando respuesta.
            _user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        elif command in (SystemCommand.SLEEP, SystemCommand.HIBERNATE):
            hibernate = command is SystemCommand.HIBERNATE
            # Se lanza en otro hilo: la llamada no vuelve hasta que el equipo despierta.
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _powrprof.SetSuspendState, hibernate, False, False)
        else:
            flag = {
                SystemCommand.SHUTDOWN: "/s",
                SystemCommand.RESTART: "/r",
                SystemCommand.LOGOFF: "/l",
            }[command]
            args = [self._shutdown_exe, flag] + ([] if flag == "/l" else ["/t", "0"])
            # Ruta absoluta y argumentos fijos: nunca se construye desde datos de red.
            # Popen no espera a que termine el proceso, así que no bloquea el event loop.
            subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)  # noqa: S603, ASYNC220
        log.info("Comando de sistema ejecutado: %s", command.value)

    async def close(self) -> None:
        self._com.shutdown(wait=False, cancel_futures=True)
