# Configuración

CellDeck guarda todo en una carpeta de **tu** PC, nunca en el repositorio ni dentro del .exe:

```
%APPDATA%\CellDeck\
├── config.json     ← botones, páginas, widgets y apariencia (lo que cambia el editor)
├── settings.json   ← ajustes y secretos de esta PC (PIN, tokens, OBS, Spotify)
├── backups\        ← copias automáticas de config.json antes de cada guardado
├── logs\           ← celldeck.log (los tokens salen ocultos)
└── plugins\        ← plugins externos opcionales (.py)
```

La primera vez que se abre CellDeck, `config.json` se copia de la configuración de fábrica
([src/celldeck/config/default_config.json](../src/celldeck/config/default_config.json)) y
`settings.json` se crea con un PIN y un secreto aleatorios.

> **No hay archivo `.env`.** CellDeck no lee variables de entorno para los secretos. Cada
> instalación genera los suyos en `settings.json`. Por eso no hace falta un `.env.example`.

## Lo normal: usar el editor y la bandeja

Casi nada requiere tocar archivos a mano:

| Quiero… | Dónde |
|---|---|
| Añadir, mover o borrar botones y páginas, y cambiar iconos y colores | ⚙️ → **Editar** (en la PC o por USB) |
| Cambiar el tema, el color de acento o el tamaño de los botones | ⚙️ → **Editar** → **Apariencia** |
| Conectar por WiFi y ver el QR o el PIN | Icono de la bandeja → **Modo WiFi** / **Mostrar QR / PIN** |
| Permitir editar desde el celular por WiFi | Icono de la bandeja → **Permitir edición por WiFi** |
| Expulsar todos los celulares conectados | Icono de la bandeja → **Desconectar todos los dispositivos** |
| Cambiar el PIN | Icono de la bandeja → **Nuevo PIN** |
| Abrir esta carpeta o ver el registro | Icono de la bandeja → **Abrir carpeta de configuración** / **Ver registro (log)** |
| Arrancar con Windows | Icono de la bandeja → **Iniciar con Windows** |
| Conectar OBS | Página **OBS** → **Configurar conexión** |
| Conectar Spotify | Página **Spotify** (ver [spotify.md](spotify.md)) |

## `settings.json` (avanzado)

Cierra CellDeck antes de editarlo a mano.

| Campo | Por defecto | Para qué sirve |
|---|---|---|
| `port` | `8765` | Puerto del servidor |
| `mode` | `"usb"` | `"usb"`: solo esta PC y el cable. `"wifi"`: escucha en la red y pide PIN |
| `pin` | aleatorio | PIN de 6 dígitos para emparejar celulares por WiFi |
| `secret` | aleatorio | Firma los tokens de los dispositivos. Cambiarlo los desconecta a todos |
| `allow_remote_edit` | `false` | Permite usar el editor por WiFi |
| `allowed_url_schemes` | `http, https, spotify, steam, mailto, discord, ms-settings` | Esquemas que pueden abrir los botones de enlace |
| `extra_allowed_hosts` | `[]` | Nombres extra que se aceptan en la cabecera `Host` (p. ej. `mipc.local`) |
| `token_ttl_days` | `90` | Días que dura emparejado un celular |
| `load_external_plugins` | `true` | Carga los `.py` de `%APPDATA%\CellDeck\plugins` |
| `adb_path` | `null` | Ruta a `adb.exe` si no está en el `PATH` ni en las carpetas habituales |
| `obs_host`, `obs_port`, `obs_password` | `127.0.0.1`, `4455`, `""` | Conexión con el servidor WebSocket de OBS |
| `spotify_client_id`, `spotify_refresh_token` | `""` | Tu app de Spotify y la sesión vinculada |

`obs_password`, `spotify_refresh_token`, `pin` y `secret` son **secretos**. No compartas este
archivo ni lo pegues en un issue.

## Opciones de línea de comandos

```
CellDeck.exe [--port N] [--mode usb|wifi] [--data-dir CARPETA] [--no-tray] [--debug] [--version]
```

Desde el código, `scripts\dev.bat` acepta las mismas opciones y además `--fake` (backend
simulado que no toca Windows).

## Variables de entorno (desarrollo)

| Variable | Para qué |
|---|---|
| `CELLDECK_HOME` | Usa otra carpeta de datos en lugar de `%APPDATA%\CellDeck` |
| `CELLDECK_WEB_DIR` | Sirve el frontend desde otra carpeta |
| `CELLDECK_PYTHON` | Python 3.13 que usa `scripts\build.bat` (lo usa GitHub Actions) |
| `CELLDECK_ONEDIR` | `1` = el spec de PyInstaller genera la variante en carpeta |

## Empezar de cero

Cierra CellDeck y borra (o renombra) `%APPDATA%\CellDeck`. Al abrirlo de nuevo se crea la
configuración de fábrica con un PIN nuevo.
