"""Ajustes locales (``settings.json``): seguridad, red y permisos.

A diferencia de ``config.json`` (layout y acciones), estos ajustes **nunca** se pueden
modificar desde el celular: solo desde la PC (bandeja o editando el archivo).
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from celldeck.fileutil import atomic_write_text

log = logging.getLogger(__name__)

DEFAULT_PORT = 8765
DEFAULT_URL_SCHEMES = ["http", "https", "spotify", "steam", "mailto", "discord", "ms-settings"]


def generate_pin() -> str:
    """PIN aleatorio de 6 dígitos (criptográficamente seguro)."""
    return f"{secrets.randbelow(10**6):06d}"


def generate_secret() -> str:
    """Secreto de 256 bits para firmar tokens."""
    return secrets.token_hex(32)


class Settings(BaseModel):
    """Ajustes persistentes de la instalación."""

    # extra="ignore": un settings.json de una versión más nueva no rompe una más vieja.
    model_config = ConfigDict(extra="ignore")

    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    mode: Literal["usb", "wifi"] = "usb"
    pin: str = Field(default_factory=generate_pin, pattern=r"^\d{6}$")
    secret: str = Field(default_factory=generate_secret, min_length=32)
    allow_remote_edit: bool = False
    allowed_url_schemes: list[str] = Field(default_factory=lambda: list(DEFAULT_URL_SCHEMES))
    extra_allowed_hosts: list[str] = Field(default_factory=list)
    token_ttl_days: int = Field(default=90, ge=1, le=3650)
    load_external_plugins: bool = True
    adb_path: str | None = None
    # Conexión con OBS (ver celldeck.obs). Por defecto, OBS en esta misma PC.
    obs_host: str = "127.0.0.1"
    obs_port: int = Field(default=4455, ge=1, le=65535)
    obs_password: str = ""
    # Cuenta de Spotify (ver celldeck.spotify). El Client ID no es secreto; el token sí.
    spotify_client_id: str = ""
    spotify_refresh_token: str = ""
    # Hasta qué versión se aplicó la migración de secciones (ver config.migrations).
    sections_version: int = 0

    @field_validator("allowed_url_schemes")
    @classmethod
    def _normalize_schemes(cls, value: list[str]) -> list[str]:
        return sorted({s.strip().lower().rstrip(":/") for s in value if s.strip()})

    @field_validator("extra_allowed_hosts")
    @classmethod
    def _normalize_hosts(cls, value: list[str]) -> list[str]:
        return sorted({h.strip().lower() for h in value if h.strip()})


class SettingsStore:
    """Carga y guarda ``settings.json`` de forma atómica."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.settings = Settings()

    def load(self) -> Settings:
        """Lee el archivo; si no existe lo crea. Si está corrupto lo aparta y regenera."""
        if not self.path.exists():
            log.info("Creando %s con valores por defecto", self.path)
            self.settings = Settings()
            self.save()
            return self.settings
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.settings = Settings.model_validate(data)
        except (OSError, ValueError, ValidationError) as exc:
            broken = self.path.with_name(f"settings.broken-{int(time.time())}.json")
            log.error("settings.json inválido (%s). Se mueve a %s y se regenera", exc, broken.name)
            try:
                self.path.replace(broken)
            except OSError:
                log.exception("No se pudo apartar settings.json corrupto")
            self.settings = Settings()
            self.save()
        return self.settings

    def save(self) -> None:
        text = json.dumps(self.settings.model_dump(mode="json"), indent=2, ensure_ascii=False)
        atomic_write_text(self.path, text + "\n")

    def update(self, **changes: Any) -> Settings:
        """Aplica cambios validados y guarda."""
        merged = self.settings.model_dump() | changes
        self.settings = Settings.model_validate(merged)
        self.save()
        return self.settings

    def regenerate_pin(self) -> str:
        """Nuevo PIN (los tokens ya emitidos siguen siendo válidos)."""
        return self.update(pin=generate_pin()).pin

    def revoke_all_devices(self) -> None:
        """Rota el secreto: invalida todos los tokens emitidos."""
        self.update(secret=generate_secret())
