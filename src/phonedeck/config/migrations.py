"""Cambios de una sola vez sobre instalaciones existentes.

``default_config.json`` solo se copia en la primera ejecución, así que una instalación
anterior no vería las secciones nuevas. Además, por WiFi el editor está desactivado por
defecto: sin esta migración muchos usuarios no podrían añadirlas desde el celular.

Se aplica una sola vez (queda anotado en ``settings.json``): si el usuario borra después una
de estas páginas, no vuelve a aparecer.
"""

from __future__ import annotations

import logging
from typing import Any

from phonedeck.config.models import MAX_PAGES
from phonedeck.config.settings import SettingsStore
from phonedeck.config.store import ConfigError, ConfigStore, default_config_data

log = logging.getLogger(__name__)

SECTIONS_VERSION = 1
NEW_SECTIONS = {"mixer": "mixer", "pomodoro": "pomodoro", "obs": "obs"}  # página → widget


def _unique_id(page_id: str, taken: set[str]) -> str:
    candidate = page_id
    suffix = 2
    while candidate in taken:
        candidate = f"{page_id}-{suffix}"
        suffix += 1
    return candidate


def add_new_sections(store: ConfigStore, settings_store: SettingsStore) -> None:
    """Añade las páginas de las secciones nuevas que la configuración aún no tenga."""
    if settings_store.settings.sections_version >= SECTIONS_VERSION:
        return
    if store.last_error is not None:
        return  # config.json inválido: no se toca, ya se avisa al usuario

    config = store.config
    pages: list[dict[str, Any]] = [
        page
        for page in default_config_data()["pages"]
        if page["id"] in NEW_SECTIONS and not config.has_widget(NEW_SECTIONS[page["id"]])
    ]
    room = MAX_PAGES - len(config.pages)
    if len(pages) > room:
        log.warning("No caben todas las secciones nuevas: el máximo son %d páginas", MAX_PAGES)
        pages = pages[: max(0, room)]

    if pages:
        data = config.to_json_dict()
        taken = {page["id"] for page in data["pages"]}
        for page in pages:
            page["id"] = _unique_id(page["id"], taken)
            taken.add(page["id"])
        data["pages"] += pages
        try:
            store.save(store.parse(data))
        except ConfigError:
            log.exception("No se pudieron añadir las secciones nuevas")
            return
        log.info("Secciones nuevas añadidas: %s", ", ".join(p["name"] for p in pages))
    settings_store.update(sections_version=SECTIONS_VERSION)
