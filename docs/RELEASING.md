# Publicar una versión

PhoneDeck usa [Versionado Semántico](https://semver.org/lang/es/) (`MAYOR.MENOR.PARCHE`):

- **PARCHE** (`0.1.0` → `0.1.1`): corrige errores sin cambiar cómo se usa.
- **MENOR** (`0.1.1` → `0.2.0`): funciones nuevas compatibles con la config existente.
- **MAYOR** (`0.x` → `1.0.0`): cambios que obligan al usuario a hacer algo (config incompatible,
  requisitos nuevos).

Mientras la versión empiece por `0.`, las Releases salen marcadas como *versión preliminar*.

## Publicar con GitHub Actions (lo normal)

1. Asegúrate de que `main` pasa la CI.
2. En una rama `chore/release-X.Y.Z`:
   - Cambia `__version__` en [src/phonedeck/__init__.py](../src/phonedeck/__init__.py). Es la
     única fuente de la versión: `pyproject.toml` y las propiedades del .exe la leen de ahí.
   - En [CHANGELOG.md](../CHANGELOG.md), mueve lo de `[Sin publicar]` a una sección nueva
     `## [X.Y.Z] - AAAA-MM-DD` y actualiza los enlaces del final.
3. Fusiona el PR y crea la etiqueta en ese commit de `main`:

   ```bat
   git switch main
   git pull
   git tag -a vX.Y.Z -m "PhoneDeck X.Y.Z"
   git push origin vX.Y.Z
   ```

4. El flujo [release.yml](../.github/workflows/release.yml) hace lo siguiente:
   1. Comprueba que la etiqueta coincide con `__version__` y con el CHANGELOG.
   2. Ejecuta los tests.
   3. Compila con las dependencias fijadas por hash y pasa `pip-audit`.
   4. Genera `PhoneDeck.exe`, `PhoneDeck-win64.zip` y `SHA256SUMS.txt`.
   5. Firma una atestación de compilación.
   6. Crea un **borrador** de Release.
5. Descarga los archivos del borrador, pruébalos en una PC con Windows y pulsa
   **Publish release**. Hasta entonces nadie más ve el borrador.

Si algo falla después de crear la etiqueta, bórrala, corrige el problema y vuelve a crearla:

```bat
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
```

Borra también el borrador de Release si se llegó a crear.

## Compilar en local (sin GitHub)

Requisitos: Windows 10/11 x64, [Python 3.13](https://www.python.org/downloads/) y un entorno
`.venv` con las herramientas de desarrollo (para `pip-audit`):

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
```

Compilar:

```bat
scripts\build.bat
powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
```

- `build.bat` crea `.venv-build` desde cero e instala versiones exactas verificadas por SHA-256
  ([requirements/build.lock](../requirements/build.lock)). Pasa `pip-audit` y genera
  `dist\PhoneDeck.exe`.
- `package_release.ps1` genera la variante en carpeta y deja en `release\` lo mismo que publica
  GitHub: `PhoneDeck.exe`, `PhoneDeck-win64.zip`, `SHA256SUMS.txt` y `NOTES.md`.

Para subirlo a mano: **Releases → Draft a new release**, elige la etiqueta, pega `NOTES.md` y
adjunta los tres archivos. Esa Release no tendrá atestación, porque solo GitHub Actions puede
firmarla.

## Actualizar las dependencias del ejecutable

```bat
.venv\Scripts\python scripts\lock_deps.py
.venv\Scripts\pip-audit -r requirements\build.lock --require-hashes --disable-pip
```

Mantén [requirements/build.in](../requirements/build.in) sincronizado con
`[project.dependencies]` de `pyproject.toml`.

## Por qué no está firmado

Firmar el ejecutable evitaría el aviso de SmartScreen, pero exige un certificado de firma de
código, que es de pago o requiere verificar una identidad. Como alternativa, cada Release publica
su SHA-256 y una atestación de GitHub que demuestra de qué commit salió:

```bat
gh attestation verify PhoneDeck.exe --repo <dueño>/<repo>
```
