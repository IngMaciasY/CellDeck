"""Orquestador: construye el estado, la app web y arranca el servidor."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from pathlib import Path

from phonedeck import paths
from phonedeck.server import create_app, run_server
from phonedeck.state import AppState, build_state

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LaunchOptions:
    data_dir: Path
    fake: bool = False
    mode: str | None = None  # None = el de settings.json
    port: int | None = None


class PortInUseError(RuntimeError):
    pass


def bind_host(mode: str) -> str:
    """USB = solo loopback; WiFi = todas las interfaces."""
    return "0.0.0.0" if mode == "wifi" else "127.0.0.1"  # noqa: S104 - modo WiFi explícito


def ensure_port_free(host: str, port: int) -> None:
    """Falla con un mensaje claro si el puerto ya está ocupado (p. ej. otra instancia)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as exc:
            raise PortInUseError(
                f"El puerto {port} ya está en uso. ¿PhoneDeck ya se está ejecutando?"
            ) from exc


def prepare(options: LaunchOptions) -> tuple[AppState, str, int]:
    state = build_state(
        options.data_dir,
        fake=options.fake,
        mode_override=options.mode,
        plugin_dirs=paths.external_plugin_dirs(),
    )
    host = bind_host(state.mode)
    port = options.port or state.settings.port
    return state, host, port


def serve(options: LaunchOptions) -> None:
    """Arranca el servidor en el hilo actual (bloqueante)."""
    from phonedeck.services import BACKGROUND_SERVICES

    state, host, port = prepare(options)
    ensure_port_free(host, port)
    app = create_app(state, web_dir=paths.web_dir(), background=list(BACKGROUND_SERVICES))
    log.info("Escuchando en http://%s:%d", host, port)
    if state.mode == "wifi":
        log.info("Modo WiFi activo. PIN de emparejamiento: %s", state.settings.pin)
    run_server(app, host, port).run()
