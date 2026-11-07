# PhoneDeck

Dashboard personalizable para controlar una PC Windows desde un celular Android antiguo
(probado como objetivo: Xiaomi Redmi 5 Plus, Android 7/8, Chrome 60+). Sin instalar apps:
el celular abre una página web servida por la PC, por cable USB (`adb reverse`) o WiFi.

> 🚧 **En desarrollo.** Hitos completados: (a) servidor, (b) interfaz del celular, (c) datos en vivo, (d) editor visual y (e) bandeja + .exe.
>
> Funciona en celulares viejos (Chrome 60+, p. ej. Xiaomi Redmi 5 Plus), celulares nuevos,
> tablets y también iPhone/iPad por WiFi: las columnas se adaptan solas a cada pantalla.

## Estado por hitos

- [x] (a) Servidor FastAPI, config con recarga en caliente, plugins `media`, `volume`,
      `launch`, `url`, `keys`, `macro`, `system`, seguridad (token, PIN, Host)
- [x] (b) UI del celular: páginas, grid táctil, widgets, PIN, pantalla completa,
      pantalla siempre encendida, reconexión automática (Chrome 60+)
- [x] (c) Ahora suena con portada, volumen en vivo con slider, CPU/RAM y columnas
      automáticas para cualquier tamaño de pantalla
- [x] (d) Editor visual desde el celular o la PC: crear, editar, mover (arrastrando) y borrar
      botones, widgets y páginas; macros paso a paso; apariencia; guardado con control de conflictos
- [x] (e) `PhoneDeck.exe` sin consola con icono en la bandeja: QR/PIN, conectar USB, modo WiFi,
      edición remota, desconectar dispositivos, iniciar con Windows
- [ ] (f) CI/CD y documentación completa

## Volume Mixer, Pomodoro y OBS

Aparecen como páginas nuevas al actualizar. Son widgets normales: se pueden mover o quitar
con el editor, y al quitar uno el celular pierde ese control.

- **Volume Mixer:** volumen y silencio por aplicación, con nombre e icono, sincronizado con
  Windows. Usa el dispositivo de salida predeterminado.
- **Pomodoro:** trabajo, descanso corto y descanso largo (tras 4 periodos de trabajo). El
  temporizador corre en la PC y los tiempos se ajustan desde el celular, también por WiFi. Al
  terminar cada periodo avisa en el celular y con una notificación de Windows (esta última
  necesita el icono de la bandeja). Si cambias entre USB y WiFi se reinicia el temporizador.
- **OBS:** un botón por escena, con la activa resaltada. Requiere OBS 28 o posterior.

### Conectar OBS

1. En OBS, abre **Herramientas** y entra a los ajustes del servidor WebSocket.
2. Activa el servidor y copia la contraseña.
3. En PhoneDeck, abre la página **OBS** desde la PC o con el celular por USB, toca
   **Configurar conexión** y pégala. Por WiFi este formulario no aparece.

PhoneDeck se conecta a OBS desde la PC, así que OBS no necesita abrirse a la red.

## Spotify

La página **Spotify** muestra tus playlists y sus canciones, y controla la música que suena en
la PC. Requiere Spotify Premium y crear una app gratuita en el panel de Spotify. Sigue los pasos
de [docs/spotify.md](docs/spotify.md).

Spotify es una marca de Spotify AB. Este proyecto no está afiliado a Spotify, y su logo no forma
parte de la licencia MIT.

## El engranaje

**Editar**, **Pantalla completa** y **Ajustes** están en el botón de engranaje. Solo aparece lo
que se puede usar en ese dispositivo. Si solo queda Ajustes, el engranaje lo abre directamente.

## Usar PhoneDeck.exe

1. Ejecuta `PhoneDeck.exe`: aparece un icono junto al reloj de Windows.
2. Clic derecho en el icono → **Conectar celular por USB** (o **Modo WiFi** + **Mostrar QR / PIN**).
3. En el celular se abre `http://localhost:8765` (por cable) o escanea el QR (WiFi).

Compilarlo tú mismo: `scripts\build.bat` → `dist\PhoneDeck.exe` (dependencias fijadas por hash
en `requirements\build.lock` y auditadas con pip-audit).

## Desarrollo rápido

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
scripts\dev.bat              :: backend real de Windows (con icono en la bandeja)
scripts\dev.bat --no-tray    :: solo el servidor, sin bandeja
scripts\dev.bat --fake       :: modo demo: backend simulado con canción de prueba
```

Probar acciones sin celular (en otra terminal):

```powershell
.\scripts\try_action.ps1 -List
.\scripts\try_action.ps1 media play-pause
```

Conectar el celular por cable: ver [docs/usb.md](docs/usb.md).

Calidad:

```bat
bun install --frozen-lockfile   :: ESLint (solo herramientas, auditado con bun audit)
bun run lint                    :: verifica compatibilidad con Chrome 60
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests plugins
.venv\Scripts\mypy
```

## Licencia

[MIT](LICENSE)
