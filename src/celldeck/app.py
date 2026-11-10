"""Orquestador: construye el estado y la app web, y arranca/para el servidor."""

from __future__ import annotations

import dataclasses
import logging
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from celldeck import paths
from celldeck.server import create_app, run_server
from celldeck.state import AppState, build_state

log = logging.getLogger(__name__)

START_TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class LaunchOptions:
    data_dir: Path
    fake: bool = False
    mode: str | None = None  # None = el de settings.json
    port: int | None = None


class PortInUseError(RuntimeError):
    pass


class ServerStartError(RuntimeError):
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
                f"El puerto {port} ya está en uso. ¿CellDeck (u otro programa) ya se está "
                "ejecutando?"
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


def _build_server(options: LaunchOptions) -> tuple[AppState, uvicorn.Server, str, int]:
    from celldeck.services import BACKGROUND_SERVICES

    state, host, port = prepare(options)
    ensure_port_free(host, port)
    app = create_app(state, web_dir=paths.web_dir(), background=list(BACKGROUND_SERVICES))
    return state, run_server(app, host, port), host, port


def serve(options: LaunchOptions) -> None:
    """Arranca el servidor en el hilo actual (bloqueante). Modo ``--no-tray``."""
    state, server, host, port = _build_server(options)
    log.info("Escuchando en http://%s:%d", host, port)
    if state.mode == "wifi":
        log.info("Modo WiFi activo. PIN de emparejamiento: %s", state.settings.pin)
    server.run()


class ServerController:
    """Ejecuta el servidor en un hilo de fondo (la bandeja ocupa el hilo principal)."""

    def __init__(self, options: LaunchOptions) -> None:
        self.options = options
        self.state: AppState | None = None
        self.port: int = 0
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._notifier: Callable[[str, str], None] | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_notifier(self, notifier: Callable[[str, str], None]) -> None:
        """Función que muestra notificaciones de Windows (también tras cada reinicio)."""
        self._notifier = notifier
        if self.state is not None:
            self.state.notifier = notifier

    def panel_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        """Arranca y espera a que el servidor esté escuchando.

        Raises:
            PortInUseError: puerto ocupado.
            ServerStartError: el servidor no llegó a arrancar (ver log).
        """
        with self._lock:
            state, server, host, port = _build_server(self.options)
            state.notifier = self._notifier
            thread = threading.Thread(target=server.run, name="celldeck-server", daemon=True)
            thread.start()
            deadline = time.monotonic() + START_TIMEOUT_S
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    server.should_exit = True
                    raise ServerStartError("El servidor no pudo arrancar (revisa el log)")
                time.sleep(0.05)
            self.state, self._server, self._thread, self.port = state, server, thread, port
            log.info("Servidor en http://%s:%d (modo %s)", host, port, state.mode)

    def stop(self, timeout: float = 8.0) -> None:
        with self._lock:
            if self._server is not None:
                self._server.should_exit = True
            if self._thread is not None:
                self._thread.join(timeout)
                if self._thread.is_alive():
                    log.warning("El servidor no se detuvo a tiempo")
            self._server = None
            self._thread = None

    def restart(self, mode: str | None = None) -> None:
        """Reinicia (p. ej. al cambiar entre USB y WiFi, que cambia la interfaz de escucha)."""
        self.stop()
        if mode is not None:
            # El modo elegido en la bandeja se guarda en settings.json; ya no se fuerza.
            self.options = dataclasses.replace(self.options, mode=None)
        # Windows puede tardar un instante en liberar el puerto.
        for attempt in range(10):
            try:
                self.start()
                return
            except PortInUseError:
                if attempt == 9:
                    raise
                time.sleep(0.3)
