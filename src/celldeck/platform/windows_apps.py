"""Localizar aplicaciones instaladas y extraer sus iconos (solo Windows).

- ``locate(spec)``: busca el ejecutable de una app del catálogo en el registro, vswhere,
  App Paths, protocolos, desinstaladores, carpetas habituales y PATH (ver celldeck.apps).
- ``resolve_target(target)``: ejecutable asociado a una ruta, nombre (``notepad.exe``) o URI.
- ``extract_icon_png(path)``: icono del .exe como PNG con transparencia (el logotipo oficial
  de la app, sin redistribuir archivos de marcas en el repositorio).

Leer recursos de un .exe no lo ejecuta: es seguro extraer iconos de rutas de la config.
"""

from __future__ import annotations

import ctypes
import io
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
from ctypes import wintypes

from celldeck.apps import AppSpec
from celldeck.platform.base import AppLocation

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("Solo Windows")

import winreg

log = logging.getLogger(__name__)

_HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
_UNINSTALL_KEYS = (
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
)
_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
CREATE_NO_WINDOW = 0x08000000


# ------------------------------------------------------------------ registro
def reg_read(hive: int, key: str, value: str = "") -> str | None:
    """Lee un valor de texto probando las vistas de 64 y 32 bits del registro."""
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as k:
                data, kind = winreg.QueryValueEx(k, value)
        except OSError:
            continue
        if isinstance(data, str) and data.strip():
            return winreg.ExpandEnvironmentStrings(data) if kind == winreg.REG_EXPAND_SZ else data
    return None


def clean_path(raw: str | None) -> str | None:
    """Normaliza una ruta del registro: comillas, ",0" de índice de icono, %VARIABLES%."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        text = text[1:end] if end > 0 else text[1:]
    else:
        text = re.sub(r",\s*-?\d+$", "", text)
    path = os.path.normpath(os.path.expandvars(text))
    return path if os.path.isfile(path) else None


def exe_from_command(command: str | None) -> str | None:
    """'"D:\\APPS\\Steam\\steam.exe" -- "%1"' → 'D:\\APPS\\Steam\\steam.exe'."""
    if not command:
        return None
    text = command.strip()
    if text.startswith('"'):
        return clean_path(text)
    match = re.match(r"(.+?\.exe)\b", text, re.IGNORECASE)
    return clean_path(match.group(1)) if match else None


def protocol_handler(scheme: str) -> str | None:
    return exe_from_command(reg_read(winreg.HKEY_CLASSES_ROOT, rf"{scheme}\shell\open\command"))


def app_path(exe: str) -> str | None:
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        found = clean_path(reg_read(hive, rf"{_APP_PATHS}\{exe}"))
        if found:
            return found
    return None


def _uninstall_entries() -> list[tuple[str, str | None, str | None]]:
    """(DisplayName, DisplayIcon, InstallLocation) de "Agregar o quitar programas"."""
    entries = []
    for hive, base in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(hive, base) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                            name = winreg.QueryValueEx(sub, "DisplayName")[0]
                            icon = _opt_value(sub, "DisplayIcon")
                            location = _opt_value(sub, "InstallLocation")
                            entries.append((str(name), icon, location))
                    except OSError:
                        continue
        except OSError:
            continue
    return entries


def _opt_value(key: winreg.HKEYType, name: str) -> str | None:
    try:
        value = winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None
    return str(value) if value else None


def _from_uninstall(spec: AppSpec) -> str | None:
    exe_names = {e.lower() for e in spec.exe_names}
    for name, icon, location in _uninstall_entries():
        if not any(name.startswith(prefix) for prefix in spec.uninstall_names):
            continue
        icon_path = clean_path(icon)
        if icon_path and os.path.basename(icon_path).lower() in exe_names:
            return icon_path
        if location:
            for exe in spec.exe_names:
                candidate = clean_path(os.path.join(location, exe))
                if candidate:
                    return candidate
    return None


def _from_vswhere() -> str | None:
    vswhere = os.path.expandvars(
        r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    )
    if not os.path.isfile(vswhere):
        return None
    try:
        out = subprocess.run(  # noqa: S603 - herramienta oficial de Microsoft, argumentos fijos
            [vswhere, "-latest", "-prerelease", "-property", "productPath"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return clean_path(out.splitlines()[0]) if out else None


def locate(spec: AppSpec) -> AppLocation | None:
    """Busca la app sin depender de una ruta fija (ver orden en celldeck.apps)."""
    strategies = [
        *(
            (
                "registro",
                lambda rv=rv: (
                    clean_path(reg_read(_HIVES[rv.hive], rv.key, rv.value))
                    if rv.kind == "file"
                    else clean_path(
                        os.path.join(
                            reg_read(_HIVES[rv.hive], rv.key, rv.value) or "", spec.exe_names[0]
                        )
                    )
                ),
            )
            for rv in spec.registry
        ),
        ("vswhere", _from_vswhere if spec.vswhere else lambda: None),
        *(("App Paths", lambda e=e: app_path(e)) for e in spec.exe_names),
        ("protocolo", lambda: protocol_handler(spec.scheme) if spec.scheme else None),
        ("desinstalador", lambda: _from_uninstall(spec) if spec.uninstall_names else None),
        *(("carpeta habitual", lambda c=c: clean_path(c)) for c in spec.candidates),
        *(("PATH", lambda e=e: clean_path(shutil.which(e))) for e in spec.exe_names),
    ]
    for source, strategy in strategies:
        try:
            path = strategy()
        except OSError:
            log.debug("Estrategia %s falló para %s", source, spec.id, exc_info=True)
            continue
        if path:
            return AppLocation(path=path, uri=spec.uri, source=source)
    if spec.scheme and reg_read(winreg.HKEY_CLASSES_ROOT, spec.scheme, "URL Protocol") is not None:
        return AppLocation(path=None, uri=spec.uri, source="protocolo")
    return None


def resolve_target(target: str) -> str | None:
    """Ejecutable para mostrar el icono de una ruta, un nombre de programa o una URI."""
    text = target.strip()
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]+):", text)
    if match and not re.match(r"^[a-zA-Z]:[\\/]", text):  # URI (no "C:\...")
        scheme = match.group(1).lower()
        if scheme in ("http", "https"):
            prog_id = reg_read(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{scheme}\UserChoice",
                "ProgId",
            )
            return (
                exe_from_command(
                    reg_read(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command")
                )
                if prog_id
                else None
            )
        return protocol_handler(scheme)
    path = clean_path(text)
    if path:
        return path
    name = os.path.basename(text)
    if name == text:  # "notepad.exe": App Paths o PATH
        return app_path(name) or clean_path(shutil.which(name))
    return None


# ------------------------------------------------------------- iconos (GDI)
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_version = ctypes.WinDLL("version", use_last_error=True)
_version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p)
_version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
_version.GetFileVersionInfoW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
)
_version.GetFileVersionInfoW.restype = wintypes.BOOL
_version.VerQueryValueW.argtypes = (
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.UINT),
)
_version.VerQueryValueW.restype = wintypes.BOOL
_user32.PrivateExtractIconsW.argtypes = (
    wintypes.LPCWSTR,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(wintypes.HICON),
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
    wintypes.UINT,
)
_user32.PrivateExtractIconsW.restype = wintypes.UINT
_user32.DrawIconEx.argtypes = (
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HICON,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.HBRUSH,
    wintypes.UINT,
)
_user32.DestroyIcon.argtypes = (wintypes.HICON,)
_gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateDIBSection.argtypes = (
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFOHEADER),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
)
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
_gdi32.DeleteDC.argtypes = (wintypes.HDC,)

DI_NORMAL = 0x0003
EXTRACT_SIZE = 256


def _render(hicon: int, size: int, background: int) -> bytes:
    """Dibuja el icono sobre un fondo liso (0x00 o 0xFF) y devuelve los píxeles BGRA."""
    hdc = _gdi32.CreateCompatibleDC(None)
    header = BITMAPINFOHEADER(
        biSize=ctypes.sizeof(BITMAPINFOHEADER),
        biWidth=size,
        biHeight=-size,  # de arriba a abajo
        biPlanes=1,
        biBitCount=32,
        biCompression=0,
    )
    bits = ctypes.c_void_p()
    hbmp = _gdi32.CreateDIBSection(hdc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    if not hbmp or not bits.value:
        _gdi32.DeleteDC(hdc)
        raise OSError("CreateDIBSection falló")
    old = _gdi32.SelectObject(hdc, hbmp)
    try:
        ctypes.memset(bits, background, size * size * 4)
        _user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, DI_NORMAL)
        return ctypes.string_at(bits, size * size * 4)
    finally:
        _gdi32.SelectObject(hdc, old)
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(hdc)


def file_description(path: str) -> str | None:
    """Nombre legible de un ejecutable ("Brave Browser"), leído de sus datos de versión."""
    size = _version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not _version.GetFileVersionInfoW(path, 0, size, data):
        return None
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    found = _version.VerQueryValueW(
        data, r"\VarFileInfo\Translation", ctypes.byref(pointer), ctypes.byref(length)
    )
    if not found or length.value < 4 or not pointer.value:
        return None
    language, codepage = struct.unpack("<HH", ctypes.string_at(pointer.value, 4))
    entry = rf"\StringFileInfo\{language:04x}{codepage:04x}\FileDescription"
    if not _version.VerQueryValueW(data, entry, ctypes.byref(pointer), ctypes.byref(length)):
        return None
    if not length.value or not pointer.value:
        return None
    return ctypes.wstring_at(pointer.value).strip() or None


def extract_icon_png(path: str, size: int = 160) -> bytes | None:
    """Icono del ejecutable como PNG cuadrado de ``size`` px con transparencia.

    Se dibuja sobre negro y sobre blanco: la diferencia da el canal alfa exacto, sirve
    tanto para iconos modernos (32 bits con alfa) como para iconos antiguos con máscara.
    """
    from PIL import Image, ImageChops

    hicon = wintypes.HICON()
    icon_id = wintypes.UINT()
    count = _user32.PrivateExtractIconsW(
        path, 0, EXTRACT_SIZE, EXTRACT_SIZE, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0
    )
    if count in (0, 0xFFFFFFFF) or not hicon.value:
        return None
    try:
        on_black = _render(hicon.value, EXTRACT_SIZE, 0x00)
        on_white = _render(hicon.value, EXTRACT_SIZE, 0xFF)
    finally:
        _user32.DestroyIcon(hicon)

    black = Image.frombuffer("RGBA", (EXTRACT_SIZE, EXTRACT_SIZE), on_black, "raw", "BGRA", 0, 1)
    white = Image.frombuffer("RGBA", (EXTRACT_SIZE, EXTRACT_SIZE), on_white, "raw", "BGRA", 0, 1)
    black_rgb, white_rgb = black.convert("RGB"), white.convert("RGB")
    # alfa = 255 - (blanco - negro). Sobre negro, el color ya está multiplicado por el alfa:
    # el modo "RGBa" (premultiplicado) de Pillow lo deshace al convertir a RGBA.
    alpha = ImageChops.invert(ImageChops.subtract(white_rgb, black_rgb).split()[1])
    img = Image.merge("RGBa", (*black_rgb.split(), alpha)).convert("RGBA")
    if img.getbbox() is None:  # todo transparente: icono vacío
        return None
    if size != EXTRACT_SIZE:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
