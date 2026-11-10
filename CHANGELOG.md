# Registro de cambios

Todos los cambios visibles de PhoneDeck se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/): `MAYOR.MENOR.PARCHE`.

## [Sin publicar]

## [0.1.0] - 2026-11-09

Primera versión pública.

### Añadido

- Servidor en la PC (FastAPI y WebSocket) que se usa desde el navegador del celular, sin
  instalar apps. Funciona por cable USB (`adb reverse`) o por WiFi con PIN.
- Interfaz del celular compatible desde Chrome 60 (Android antiguos), celulares nuevos,
  tablets, iPhone y iPad. Las columnas se adaptan a cada pantalla.
- Botones para multimedia, volumen, abrir programas y carpetas, enlaces, atajos de teclado,
  macros paso a paso y acciones del sistema (bloquear, apagar la pantalla, suspender).
- Botones de aplicaciones instaladas (Steam, Epic Games, Visual Studio, VS Code, Brave) que las
  encuentran sin rutas fijas y muestran su logotipo oficial.
- Widgets en vivo: Ahora suena con portada, volumen, CPU y RAM, y reloj.
- Volume Mixer por aplicación, temporizador Pomodoro y cambio de escena en OBS (opcional).
- Integración opcional con Spotify. Cada usuario usa su propio Client ID.
- Editor visual desde el celular o la PC: botones, widgets, páginas, iconos, colores y macros.
- `PhoneDeck.exe` con icono en la bandeja: QR y PIN, conexión USB, modo WiFi, desconectar
  dispositivos e iniciar con Windows.
- Releases automáticas en GitHub: `PhoneDeck.exe`, `PhoneDeck-win64.zip`, SHA-256 y atestación
  de compilación.

[Sin publicar]: ../../compare/v0.1.0...HEAD
[0.1.0]: ../../releases/tag/v0.1.0
