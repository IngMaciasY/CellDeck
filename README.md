# PhoneDeck

Dashboard personalizable para controlar una PC Windows desde un celular Android antiguo
(probado como objetivo: Xiaomi Redmi 5 Plus, Android 7/8, Chrome 60+). Sin instalar apps:
el celular abre una página web servida por la PC, por cable USB (`adb reverse`) o WiFi.

> 🚧 **En desarrollo.** Hitos completados: (a) servidor, (b) interfaz del celular y (c) datos en vivo.
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
- [ ] (d) Editor visual
- [ ] (e) Bandeja + `PhoneDeck.exe`
- [ ] (f) CI/CD y documentación completa

## Desarrollo rápido

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
scripts\dev.bat              :: backend real de Windows
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
