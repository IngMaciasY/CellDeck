# Cómo contribuir a PhoneDeck

¡Gracias por querer ayudar! Esta guía explica cómo preparar tu entorno, crear una rama y enviar
un Pull Request (PR).

## Flujo de trabajo: GitHub Flow

- `main` siempre debe funcionar. Nadie sube cambios directamente a `main`.
- Cada cambio vive en su propia rama y entra a `main` mediante un Pull Request.
- Un PR solo se fusiona si pasa la integración continua (lint y tests) y alguien lo revisa.
- Las versiones publicadas se marcan con etiquetas `vX.Y.Z` (ver [docs/RELEASING.md](docs/RELEASING.md)).

### Nombres de rama

| Prefijo     | Para qué                               | Ejemplo                    |
|-------------|----------------------------------------|----------------------------|
| `feat/`     | Una función nueva                      | `feat/widget-clima`        |
| `fix/`      | Corregir un error                      | `fix/pin-con-ceros`        |
| `docs/`     | Solo documentación                     | `docs/guia-iphone`         |
| `refactor/` | Reorganizar código sin cambiar su uso  | `refactor/servicios`       |
| `test/`     | Añadir o mejorar tests                 | `test/mixer-sin-audio`     |
| `chore/`    | Mantenimiento, dependencias, scripts   | `chore/actualizar-fastapi` |

## Paso a paso

### 1. Haz un fork y clónalo

Si no tienes permiso de escritura en el repositorio, pulsa **Fork** en GitHub y clona tu copia:

```bat
git clone https://github.com/<tu-usuario>/PhoneDeck.git
cd PhoneDeck
git remote add upstream https://github.com/IngMaciasY/PhoneDeck.git
```

### 2. Prepara el entorno

Necesitas **Windows 10/11**, **Python 3.13** y **Git**. Para el lint del frontend, también
[bun](https://bun.sh).

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
bun install --frozen-lockfile
```

Ejecútalo en modo demo, que no toca tu sistema:

```bat
scripts\dev.bat --fake --no-tray
```

Abre `http://localhost:8765` en el navegador de la PC.

### 3. Crea tu rama desde un `main` actualizado

```bat
git switch main
git pull upstream main
git switch -c feat/mi-cambio
```

### 4. Haz tus cambios y compruébalos

Antes de enviar el PR, ejecuta lo mismo que la integración continua:

```bat
.venv\Scripts\ruff check src tests plugins scripts
.venv\Scripts\ruff format --check src tests plugins scripts
.venv\Scripts\mypy
.venv\Scripts\python -m pytest
bun run lint
```

Algunas reglas del proyecto:

- **El frontend debe funcionar en Chrome 60** (celulares Android viejos). `bun run lint` lo
  comprueba. No uses sintaxis ni APIs más nuevas sin un respaldo.
- **No añadas dependencias sin auditarlas.** En Python, ejecuta `pip-audit`. En JavaScript,
  `bun install --lockfile-only`, después `bun audit` y luego `bun install --frozen-lockfile`.
  Si cambias las dependencias del ejecutable, regenera `requirements/build.lock` con
  `python scripts/lock_deps.py`.
- **Los archivos `.bat` deben ser ASCII con finales CRLF**, o `cmd.exe` los rompe.
- **Nunca subas datos personales:** ni tu `config.json` o `settings.json` (están en
  `%APPDATA%\PhoneDeck`), ni Client IDs, tokens, contraseñas o rutas de tu PC.
- **Las decisiones de diseño importantes** se anotan en [DECISIONS.md](DECISIONS.md): qué se
  eligió, qué se descartó y por qué.

### 5. Haz commits con Conventional Commits

```
tipo(ámbito): descripción breve en presente
```

Ejemplos: `feat(widgets): widget de clima`, `fix(usb): reintentar adb reverse`,
`docs: guía para iPhone`. Los tipos son los mismos que los prefijos de rama, más `perf`,
`build` y `ci`.

### 6. Sube la rama y abre el Pull Request

```bat
git push -u origin feat/mi-cambio
```

En GitHub pulsa **Compare & pull request** y completa la plantilla. Explica qué cambia, por qué
y cómo lo probaste. Si el cambio no se pudo probar en un celular o una PC real, dilo.

## Reportar errores o proponer ideas

Usa las plantillas de **Issues**. Para vulnerabilidades de seguridad **no abras un issue
público**: sigue [SECURITY.md](SECURITY.md).

## Licencia

Al contribuir aceptas que tu código se publique bajo la [licencia MIT](LICENSE) del proyecto.
