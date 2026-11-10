"""Conexión por cable USB con ``adb reverse`` (equivalente a scripts/connect_usb.bat)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
TIMEOUT_S = 20

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]

_CANDIDATES = (
    r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe",
    r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe",
    r"C:\platform-tools\adb.exe",
    r"%ProgramFiles%\platform-tools\adb.exe",
    r"%USERPROFILE%\platform-tools\adb.exe",
)


@dataclass
class AdbResult:
    ok: bool
    message: str
    devices: list[str] = field(default_factory=list)


def find_adb(configured: str | None = None) -> str | None:
    """Busca adb: ruta de settings.json, PATH y ubicaciones habituales."""
    if configured and Path(os.path.expandvars(configured)).is_file():
        return os.path.expandvars(configured)
    found = shutil.which("adb")
    if found:
        return found
    for cand in _CANDIDATES:
        path = Path(os.path.expandvars(cand))
        if path.is_file():
            return str(path)
    return None


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # Sin ventana de consola (el .exe es una app de bandeja). Argumentos fijos: nunca
    # se construyen con datos recibidos por la red.
    flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(  # noqa: S603
        list(args),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        creationflags=flags,
        check=False,
    )


def parse_devices(output: str) -> list[tuple[str, str]]:
    """Salida de ``adb devices`` → [(serie, estado)]."""
    result = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            result.append((parts[0], parts[1]))
    return result


def connect_usb(
    port: int,
    adb_path: str | None = None,
    open_page: bool = True,
    runner: Runner | None = None,
) -> AdbResult:
    """Crea el túnel ``adb reverse tcp:PORT tcp:PORT`` en cada celular conectado.

    Si ``open_page``, abre ``http://localhost:PORT/`` en el celular (con ``http://``
    explícito: los Chrome modernos intentan https si se escribe sin esquema).
    """
    run = runner or _default_runner
    adb = find_adb(adb_path)
    if adb is None:
        return AdbResult(
            False,
            "No se encontró adb. Instala 'SDK Platform-Tools' de Android y añádelo al PATH "
            "(ver docs/usb.md).",
        )
    try:
        run([adb, "start-server"])
        devices = parse_devices(run([adb, "devices"]).stdout)
    except (OSError, subprocess.SubprocessError) as exc:
        log.exception("Fallo ejecutando adb")
        return AdbResult(False, f"No se pudo ejecutar adb: {exc}")

    ready = [serial for serial, st in devices if st == "device"]
    if not ready:
        if any(st == "unauthorized" for _, st in devices):
            return AdbResult(
                False,
                "El celular no autorizó esta PC: desbloquéalo y acepta 'Permitir depuración USB'.",
            )
        return AdbResult(
            False,
            "No hay ningún celular conectado. Revisa el cable (de datos) y que la "
            "depuración USB esté activada.",
        )

    connected: list[str] = []
    errors: list[str] = []
    for serial in ready:
        res = run([adb, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"])
        if res.returncode != 0:
            errors.append(f"{serial}: {(res.stderr or res.stdout).strip()}")
            continue
        model = run([adb, "-s", serial, "shell", "getprop", "ro.product.model"]).stdout.strip()
        connected.append(model or serial)
        if open_page:
            run(
                [
                    adb,
                    "-s",
                    serial,
                    "shell",
                    "am",
                    "start",
                    "-a",
                    "android.intent.action.VIEW",
                    "-d",
                    f"http://localhost:{port}/",
                ]
            )
    if not connected:
        return AdbResult(False, "adb reverse falló: " + "; ".join(errors))
    log.info("Túnel USB creado para: %s", ", ".join(connected))
    return AdbResult(True, "Conectado: " + ", ".join(connected), connected)
