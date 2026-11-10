# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/PhoneDeck.exe (un único archivo, sin consola, con icono).
# Uso: pyinstaller --clean --noconfirm phonedeck.spec   (o scripts\build.bat)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH)  # noqa: F821 - variable inyectada por PyInstaller
sys.path.insert(0, str(ROOT / "src"))
from phonedeck import __version__  # noqa: E402

_nums = tuple(int(x) for x in __version__.split(".")[:3]) + (0,)

# Metadatos visibles en Propiedades → Detalles del .exe
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_nums, prodvers=_nums),
    kids=[
        StringFileInfo([
            StringTable("0C0A04B0", [
                StringStruct("CompanyName", "PhoneDeck contributors"),
                StringStruct("FileDescription", "PhoneDeck - controla tu PC desde el celular"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "PhoneDeck"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "PhoneDeck.exe"),
                StringStruct("ProductName", "PhoneDeck"),
                StringStruct("ProductVersion", __version__),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0C0A, 1200])]),
    ],
)

hiddenimports = (
    collect_submodules("phonedeck")
    + collect_submodules("uvicorn")
    + [
        "pystray._win32",
        "pycaw.pycaw",
        "comtypes.stream",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.media.control",
        "winrt.windows.storage.streams",
    ]
)

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "assets" / "phonedeck.png"), "assets"),
    (str(ROOT / "assets" / "phonedeck.ico"), "assets"),
    (str(ROOT / "src" / "phonedeck" / "config" / "default_config.json"), "phonedeck/config"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "phonedeck" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython", "pip_audit"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

ONEDIR = os.environ.get("PHONEDECK_ONEDIR") == "1"
exe_options = {
    "name": "PhoneDeck",
    "icon": str(ROOT / "assets" / "phonedeck.ico"),
    "version": version_info,
    "console": False,  # app de bandeja: sin ventana negra
    "upx": False,  # UPX provoca falsos positivos en antivirus
    "disable_windowed_traceback": False,
}

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)  # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, name="PhoneDeck", upx=False)  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)  # noqa: F821
