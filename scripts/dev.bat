@echo off
rem ---------------------------------------------------------------------------
rem  PhoneDeck - modo desarrollo
rem  Uso:  scripts\dev.bat            (backend real de Windows)
rem        scripts\dev.bat --fake     (simulado: no toca el sistema)
rem        scripts\dev.bat --mode wifi --debug
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [PhoneDeck] No existe .venv. Crea el entorno primero:
    echo     py -3.13 -m venv .venv
    echo     .venv\Scripts\python -m pip install -e .[dev]
    exit /b 1
)

set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m phonedeck %*
