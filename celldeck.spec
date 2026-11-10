# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/CellDeck.exe (un único archivo, sin consola, con icono).
# Uso: pyinstaller --clean --noconfirm celldeck.spec   (o scripts\build.bat)
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
from celldeck import __version__  # noqa: E402

_nums = tuple(int(x) for x in __version__.split(".")[:3]) + (0,)

# Metadatos visibles en Propiedades → Detalles del .exe
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_nums, prodvers=_nums),
    kids=[
        StringFileInfo([
            StringTable("0C0A04B0", [
                StringStruct("CompanyName", "CellDeck contributors"),
                StringStruct("FileDescription", "CellDeck - controla tu PC desde el celular"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "CellDeck"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "CellDeck.exe"),
                StringStruct("ProductName", "CellDeck"),
                StringStruct("ProductVersion", __version__),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0C0A, 1200])]),
    ],
)

hiddenimports = (
    collect_submodules("celldeck")
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
    (str(ROOT / "assets" / "celldeck.png"), "assets"),
    (str(ROOT / "assets" / "celldeck.ico"), "assets"),
    (str(ROOT / "src" / "celldeck" / "config" / "default_config.json"), "celldeck/config"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "celldeck" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython", "pip_audit"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

ONEDIR = os.environ.get("CELLDECK_ONEDIR") == "1"
exe_options = {
    "name": "CellDeck",
    "icon": str(ROOT / "assets" / "celldeck.ico"),
    "version": version_info,
    "console": False,  # app de bandeja: sin ventana negra
    "upx": False,  # UPX provoca falsos positivos en antivirus
    "disable_windowed_traceback": False,
}

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)  # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, name="CellDeck", upx=False)  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)  # noqa: F821
