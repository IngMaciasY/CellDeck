"""Carga de plugins externos (archivos ``.py`` en la carpeta ``plugins`` del usuario).

Un plugin externo es un módulo que define ``PLUGINS = [MiPlugin(), ...]``.
Solo se cargan archivos locales que el propio usuario ha copiado en esa carpeta;
desde el celular no se puede subir ni modificar código.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from phonedeck.plugins.base import ActionPlugin, PluginRegistry

log = logging.getLogger(__name__)


def load_external_plugins(registry: PluginRegistry, folders: list[Path]) -> list[str]:
    """Importa los plugins de ``folders`` y los registra. Devuelve los tipos añadidos.

    Un plugin defectuoso se registra en el log y se omite: nunca impide arrancar.
    """
    added: list[str] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                added += _load_file(registry, path)
            except Exception:
                log.exception("No se pudo cargar el plugin externo %s", path)
    if added:
        log.info("Plugins externos cargados: %s", ", ".join(added))
    return added


def _load_file(registry: PluginRegistry, path: Path) -> list[str]:
    spec = importlib.util.spec_from_file_location(f"phonedeck_ext_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se puede importar {path}")
    module = importlib.util.module_from_spec(spec)
    # pydantic resuelve las anotaciones buscando el módulo en sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    plugins = getattr(module, "PLUGINS", None)
    if not isinstance(plugins, list):
        log.warning("%s no define una lista PLUGINS; se ignora", path.name)
        return []
    added: list[str] = []
    for plugin in plugins:
        if not isinstance(plugin, ActionPlugin):
            log.warning("%s: %r no es un ActionPlugin; se ignora", path.name, plugin)
            continue
        registry.register(plugin)
        added.append(plugin.type)
    return added
