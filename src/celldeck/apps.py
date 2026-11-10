"""Catálogo de aplicaciones conocidas que CellDeck sabe localizar sin rutas fijas.

Cada aplicación puede estar instalada en cualquier carpeta (p. ej. Steam en ``D:\\APPS``),
así que no se guarda una ruta: se describe *dónde la registra Windows* y la capa de
plataforma la busca en ese orden:

1. Valores de registro propios de la app (p. ej. ``HKCU\\Software\\Valve\\Steam\\SteamExe``).
2. ``vswhere`` (herramienta oficial de Microsoft para localizar Visual Studio).
3. "App Paths" de Windows (``...\\CurrentVersion\\App Paths\\<exe>``).
4. Manejador de protocolo (``HKCR\\steam\\shell\\open\\command``).
5. Entradas de "Agregar o quitar programas" (``DisplayIcon`` / ``InstallLocation``).
6. Carpetas habituales (con variables de entorno) y el ``PATH``.

Si no se encuentra el ejecutable pero el protocolo está registrado, se abre por URI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistryValue:
    """Valor de registro con la ruta del ejecutable (``kind="file"``) o su carpeta (``"dir"``)."""

    hive: str  # "HKCU" | "HKLM"
    key: str
    value: str = ""
    kind: str = "file"


@dataclass(frozen=True, slots=True)
class AppSpec:
    id: str
    name: str
    fallback_icon: str  # icono genérico si no se puede extraer el de la app
    exe_names: tuple[str, ...]
    uri: str | None = None  # alternativa si solo está registrado el protocolo
    registry: tuple[RegistryValue, ...] = ()
    uninstall_names: tuple[str, ...] = ()  # prefijos de DisplayName
    candidates: tuple[str, ...] = ()  # rutas habituales con %VARIABLES%
    vswhere: bool = False

    @property
    def scheme(self) -> str | None:
        return self.uri.split(":", 1)[0] if self.uri else None


_EPIC_BIN = r"Epic Games\Launcher\Portal\Binaries"

APPS: dict[str, AppSpec] = {
    spec.id: spec
    for spec in (
        AppSpec(
            id="steam",
            name="Steam",
            fallback_icon="gamepad",
            exe_names=("steam.exe",),
            uri="steam://open/main",
            registry=(
                RegistryValue("HKCU", r"Software\Valve\Steam", "SteamExe"),
                RegistryValue("HKLM", r"SOFTWARE\Valve\Steam", "InstallPath", "dir"),
            ),
            uninstall_names=("Steam",),
            candidates=(r"%ProgramFiles(x86)%\Steam\steam.exe", r"%ProgramFiles%\Steam\steam.exe"),
        ),
        AppSpec(
            id="epic",
            name="Epic Games Launcher",
            fallback_icon="gamepad",
            exe_names=("EpicGamesLauncher.exe",),
            uri="com.epicgames.launcher://store",
            uninstall_names=("Epic Games Launcher",),
            candidates=(
                rf"%ProgramFiles(x86)%\{_EPIC_BIN}\Win64\EpicGamesLauncher.exe",
                rf"%ProgramFiles%\{_EPIC_BIN}\Win64\EpicGamesLauncher.exe",
                rf"%ProgramFiles(x86)%\{_EPIC_BIN}\Win32\EpicGamesLauncher.exe",
            ),
        ),
        AppSpec(
            id="visualstudio",
            name="Visual Studio",
            fallback_icon="code",
            exe_names=("devenv.exe",),
            vswhere=True,
            uninstall_names=(
                "Visual Studio Community",
                "Visual Studio Professional",
                "Visual Studio Enterprise",
            ),
        ),
        AppSpec(
            id="vscode",
            name="Visual Studio Code",
            fallback_icon="code",
            exe_names=("Code.exe",),
            uri="vscode://",
            uninstall_names=("Microsoft Visual Studio Code",),
            candidates=(
                r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                r"%ProgramFiles%\Microsoft VS Code\Code.exe",
            ),
        ),
        AppSpec(
            id="brave",
            name="Brave",
            fallback_icon="globe",
            exe_names=("brave.exe",),
            uninstall_names=("Brave",),
            candidates=(
                r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
            ),
        ),
    )
}


def get_app(app_id: str) -> AppSpec | None:
    return APPS.get(app_id)
