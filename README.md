# PhoneDeck

Dashboard personalizable para controlar una PC Windows desde un celular Android antiguo
(probado como objetivo: Xiaomi Redmi 5 Plus, Android 7/8, Chrome 60+). Sin instalar apps:
el celular abre una página web servida por la PC, por cable USB (`adb reverse`) o WiFi.

> 🚧 **En desarrollo.** Hito actual: **(a) servidor + multimedia + lanzador**.
> La interfaz del celular llega en el hito (b).

## Estado por hitos

- [x] (a) Servidor FastAPI, config con recarga en caliente, plugins `media`, `volume`,
      `launch`, `url`, `keys`, `macro`, `system`, seguridad (token, PIN, Host)
- [ ] (b) UI del celular
- [ ] (c) Ahora suena + volumen + widgets en vivo
- [ ] (d) Editor visual
- [ ] (e) Bandeja + `PhoneDeck.exe`
- [ ] (f) CI/CD y documentación completa

## Desarrollo rápido

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
scripts\dev.bat              :: backend real de Windows
scripts\dev.bat --fake       :: backend simulado (no toca el sistema)
```

Probar acciones sin celular (en otra terminal):

```powershell
.\scripts\try_action.ps1 -List
.\scripts\try_action.ps1 media play-pause
```

Calidad:

```bat
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests plugins
.venv\Scripts\mypy
```

## Licencia

[MIT](LICENSE)
