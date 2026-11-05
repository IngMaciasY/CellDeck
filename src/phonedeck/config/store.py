"""Persistencia de ``config.json`` con validación, copias de seguridad y recarga en caliente."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from phonedeck.config.models import Config
from phonedeck.fileutil import atomic_write_text
from phonedeck.plugins.base import PluginRegistry

log = logging.getLogger(__name__)

MAX_BACKUPS = 10


class ConfigError(Exception):
    """La configuración no es válida. ``errors`` contiene detalles legibles."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class ConfigConflictError(Exception):
    """Se intentó guardar sobre una revisión que ya no es la actual."""


def clean_msg(msg: str) -> str:
    """Quita el prefijo técnico de pydantic ("Value error, ...") para mostrarlo al usuario."""
    return msg.removeprefix("Value error, ")


def _format_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": ".".join(str(p) for p in err["loc"]), "msg": clean_msg(err["msg"])}
        for err in exc.errors(include_url=False)
    ]


def default_config_data() -> dict[str, Any]:
    """Config de ejemplo incluida en el paquete."""
    text = resources.files("phonedeck.config").joinpath("default_config.json").read_text("utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


class ConfigStore:
    """Mantiene la config actual en memoria sincronizada con el archivo."""

    def __init__(self, path: Path, registry: PluginRegistry) -> None:
        self.path = path
        self.registry = registry
        self.backup_dir = path.parent / "backups"
        self.config: Config = self.parse(default_config_data())
        self.revision: str = self._revision_of(self.config)
        self.last_error: ConfigError | None = None
        self._stamp: tuple[int, int] | None = None

    # ------------------------------------------------------------- utilidades
    def parse(self, data: Any) -> Config:
        """Valida un dict y devuelve ``Config``; lanza :class:`ConfigError` si no es válido."""
        try:
            return Config.model_validate(data, context={"registry": self.registry})
        except ValidationError as exc:
            errors = _format_errors(exc)
            summary = "; ".join(f"{e['loc']}: {e['msg']}" for e in errors[:5])
            raise ConfigError(f"Configuración inválida: {summary}", errors) from None

    @staticmethod
    def _revision_of(config: Config) -> str:
        canonical = json.dumps(config.to_json_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _read_file(self) -> Config:
        try:
            raw = self.path.read_text(encoding="utf-8-sig")  # tolera BOM del Bloc de notas
        except OSError as exc:
            raise ConfigError(f"No se pudo leer {self.path.name}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            where = f"línea {exc.lineno} columna {exc.colno}"
            raise ConfigError(f"JSON inválido en {self.path.name}, {where}: {exc.msg}") from None
        return self.parse(data)

    def _apply(self, config: Config) -> None:
        self.config = config
        self.revision = self._revision_of(config)
        self.last_error = None

    # ------------------------------------------------------------- operaciones
    def load(self) -> Config:
        """Carga el archivo (lo crea con la config de ejemplo si no existe).

        Si el archivo es inválido, se conserva la config en memoria (la de ejemplo al
        arrancar), se guarda el error en ``last_error`` y **no** se toca el archivo.
        """
        if not self.path.exists():
            log.info("No existe %s: se crea con la configuración de ejemplo", self.path)
            self._write(self.config)
            return self.config
        try:
            self._apply(self._read_file())
            log.info("Configuración cargada: %d página(s)", len(self.config.pages))
        except ConfigError as exc:
            self.last_error = exc
            log.error("%s. Se usa la configuración anterior.", exc)
        self._stamp = self._file_stamp()
        return self.config

    def save(self, config: Config, expected_revision: str | None = None) -> str:
        """Guarda ``config`` (haciendo copia de seguridad). Devuelve la nueva revisión.

        Raises:
            ConfigConflictError: si ``expected_revision`` no coincide con la actual
                (otra pestaña o el archivo cambiaron mientras se editaba).
        """
        if expected_revision is not None and expected_revision != self.revision:
            raise ConfigConflictError("La configuración cambió mientras editabas; recarga.")
        self._backup()
        self._write(config)
        self._apply(config)
        log.info("Configuración guardada (revisión %s)", self.revision)
        return self.revision

    def _write(self, config: Config) -> None:
        text = json.dumps(config.to_json_dict(), indent=2, ensure_ascii=False) + "\n"
        atomic_write_text(self.path, text)
        self._stamp = self._file_stamp()

    def _backup(self) -> None:
        if not self.path.exists():
            return
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            target = self.backup_dir / f"config-{stamp}-{time.time_ns() % 1000:03d}.json"
            target.write_bytes(self.path.read_bytes())
            backups = sorted(self.backup_dir.glob("config-*.json"))
            for old in backups[:-MAX_BACKUPS]:
                old.unlink(missing_ok=True)
        except OSError:
            log.exception("No se pudo crear la copia de seguridad de la config")

    def check_reload(self) -> bool:
        """Recarga si el archivo cambió en disco. Devuelve ``True`` si hubo cambio válido."""
        stamp = self._file_stamp()
        if stamp is None or stamp == self._stamp:
            return False
        self._stamp = stamp
        try:
            new_config = self._read_file()
        except ConfigError as exc:
            self.last_error = exc
            log.error("Recarga fallida: %s. Se mantiene la configuración anterior.", exc)
            return False
        if self._revision_of(new_config) == self.revision:
            return False
        self._apply(new_config)
        log.info("Configuración recargada desde disco (revisión %s)", self.revision)
        return True

    async def watch(
        self, on_change: Callable[[Config], Awaitable[None]], interval: float = 1.0
    ) -> None:
        """Tarea que vigila el archivo y llama a ``on_change`` tras cada recarga válida."""
        while True:
            await asyncio.sleep(interval)
            try:
                if self.check_reload():
                    await on_change(self.config)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Error vigilando la configuración")
