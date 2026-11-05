@echo off
rem ---------------------------------------------------------------------------
rem  PhoneDeck - compilar dist\PhoneDeck.exe
rem
rem  1. Crea un entorno limpio .venv-build con Python 3.13
rem  2. Instala dependencias EXACTAS (version + hash SHA-256) de requirements\build.lock
rem  3. Audita vulnerabilidades conocidas (pip-audit), si esta disponible
rem  4. Compila con PyInstaller y calcula el SHA-256 del .exe
rem
rem  Nota: este archivo debe ser ASCII con finales de linea CRLF (cmd.exe).
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 -c "pass" >nul 2>nul
    if not errorlevel 1 set "PY=py -3.13"
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python313\python.exe""
if not defined PY (
    echo [ERROR] No se encontro Python 3.13. Instalalo desde https://www.python.org/downloads/
    echo         o con:  winget install --id Python.Python.3.13 --source winget
    exit /b 1
)

echo [1/4] Entorno de compilacion limpio .venv-build ...
if exist ".venv-build" rmdir /s /q ".venv-build"
%PY% -m venv .venv-build
if errorlevel 1 exit /b 1
set "VPY=.venv-build\Scripts\python.exe"

echo [2/4] Instalando dependencias verificadas por hash ...
"%VPY%" -m pip install --disable-pip-version-check --quiet --require-hashes --no-deps -r requirements\build.lock
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion. Si cambiaste requirements\build.in ejecuta:
    echo         python scripts\lock_deps.py
    exit /b 1
)

echo [3/4] Auditoria de vulnerabilidades ...
if exist ".venv\Scripts\pip-audit.exe" (
    ".venv\Scripts\pip-audit.exe" -r requirements\build.lock --require-hashes --disable-pip --progress-spinner off
    if errorlevel 1 (
        echo [ERROR] pip-audit encontro vulnerabilidades. Actualiza build.lock antes de publicar.
        exit /b 1
    )
) else (
    echo        pip-audit no esta en .venv: se omite. Instalalo con: .venv\Scripts\pip install pip-audit
)

echo [4/4] Compilando con PyInstaller ...
"%VPY%" -m PyInstaller --clean --noconfirm --log-level WARN phonedeck.spec
if errorlevel 1 exit /b 1

if not exist "dist\PhoneDeck.exe" (
    echo [ERROR] No se genero dist\PhoneDeck.exe
    exit /b 1
)
certutil -hashfile "dist\PhoneDeck.exe" SHA256 | findstr /v ":" > "dist\PhoneDeck.exe.sha256"
echo.
echo [OK] dist\PhoneDeck.exe
type "dist\PhoneDeck.exe.sha256"
exit /b 0
