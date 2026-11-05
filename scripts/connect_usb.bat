@echo off
rem ---------------------------------------------------------------------------
rem  PhoneDeck - conexión por cable USB con "adb reverse"
rem  Hace que http://localhost:8765 en el celular apunte al PhoneDeck de la PC.
rem  Requisitos: "Depuración USB" activada en el celular y adb instalado.
rem ---------------------------------------------------------------------------
setlocal
set "PORT=8765"
if not "%~1"=="" set "PORT=%~1"

where adb >nul 2>nul
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
        set "PATH=%LOCALAPPDATA%\Android\Sdk\platform-tools;%PATH%"
    ) else (
        echo [ERROR] No se encontro adb.
        echo         Descarga "SDK Platform-Tools" de https://developer.android.com/tools/releases/platform-tools
        echo         y descomprimelo en una carpeta incluida en el PATH.
        exit /b 1
    )
)

adb start-server >nul 2>nul
for /f "skip=1 tokens=1,2" %%a in ('adb devices') do (
    if "%%b"=="unauthorized" (
        echo [!] El celular no autorizo esta PC. Desbloquealo y acepta el dialogo "Permitir depuracion USB".
        exit /b 1
    )
)

adb reverse tcp:%PORT% tcp:%PORT%
if errorlevel 1 (
    echo [ERROR] adb reverse fallo. Revisa el cable, que la depuracion USB este activa
    echo         y que solo haya un dispositivo conectado ^(adb devices^).
    exit /b 1
)

echo.
echo [OK] Tunel creado. En el celular abre Chrome y entra en:
echo.
echo        http://localhost:%PORT%
echo.
echo Si desconectas el cable, vuelve a ejecutar este script.
exit /b 0
