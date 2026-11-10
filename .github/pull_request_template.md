## Qué cambia

<!-- Describe el cambio en pocas líneas. Enlaza el issue si existe: "Cierra #123". -->

## Por qué

## Cómo lo probé

- [ ] `ruff check`, `ruff format --check`, `mypy` y `pytest` pasan en local
- [ ] `bun run lint` pasa (compatibilidad con Chrome 60) si toqué `web/`
- [ ] Probado en un celular real (modelo y navegador: ...) / No probado en un celular real
- [ ] Probado con `CellDeck.exe` compilado (`scripts\build.bat`) / No aplica

## Lista de control

- [ ] No incluye datos personales (config, tokens, Client IDs, rutas de mi PC)
- [ ] Si añadí dependencias, las audité (pip-audit / bun audit)
- [ ] Si tomé una decisión de diseño, la anoté en `DECISIONS.md`
- [ ] Si cambia algo visible para el usuario, actualicé `README.md` y `CHANGELOG.md`
