"""Icono en la bandeja del sistema (pystray).

Menú:
    Abrir panel · Mostrar QR / PIN · Conectar celular por USB
    Modo WiFi · Permitir edición por WiFi · Nuevo PIN · Desconectar todos los dispositivos
    Iniciar con Windows · Carpeta de configuración · Ver registro · Salir
"""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from phonedeck import __version__, autostart, paths, winui
from phonedeck.adb import connect_usb
from phonedeck.app import PortInUseError, ServerController, ServerStartError

log = logging.getLogger(__name__)

TOOLTIP_REFRESH_S = 3.0


def load_icon_image() -> Image.Image:
    """Icono de assets/ (incluido en el .exe); si falta, uno dibujado al vuelo."""
    path = paths.resource_dir() / "assets" / "phonedeck.png"
    try:
        return Image.open(path).convert("RGBA")
    except OSError:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([2, 2, 62, 62], radius=14, fill=(79, 140, 255, 255))
        return img


def _open_path(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606 - ruta local propia (carpeta de datos / log)
    else:
        webbrowser.open(path.as_uri())


class TrayApp:
    def __init__(self, controller: ServerController, data_dir: Path, log_file: Path) -> None:
        controller.set_notifier(self.notify)
        self.controller = controller
        self.data_dir = data_dir
        self.log_file = log_file
        self.icon: Any = None
        self._stop = threading.Event()
        self._busy = threading.Lock()

    # ---------------------------------------------------------------- utilidades
    @property
    def state(self) -> Any:
        return self.controller.state

    def notify(self, message: str, title: str = "PhoneDeck") -> None:
        log.info("Aviso: %s", message)
        try:
            if self.icon is not None:
                self.icon.notify(message, title)
        except Exception:
            log.debug("No se pudo mostrar la notificación", exc_info=True)

    def _in_background(self, fn: Any) -> None:
        """Las acciones lentas (adb, reinicios) no deben congelar el menú."""

        def runner() -> None:
            if not self._busy.acquire(blocking=False):
                self.notify("Espera a que termine la acción anterior")
                return
            try:
                fn()
            except Exception as exc:
                log.exception("Error en acción de la bandeja")
                self.notify(f"Error: {exc}")
            finally:
                self._busy.release()
                self.refresh()

        threading.Thread(target=runner, daemon=True).start()

    def tooltip(self) -> str:
        st = self.state
        if st is None or not self.controller.running:
            return "PhoneDeck · detenido"
        mode = "WiFi" if st.mode == "wifi" else "USB"
        n = st.hub.client_count
        return f"PhoneDeck {__version__} · {mode} · {n} dispositivo{'s' if n != 1 else ''}"

    def refresh(self) -> None:
        if self.icon is None:
            return
        self.icon.title = self.tooltip()
        self.icon.update_menu()

    def _tooltip_loop(self) -> None:
        while not self._stop.wait(TOOLTIP_REFRESH_S):
            try:
                if self.icon is not None:
                    self.icon.title = self.tooltip()
            except Exception:
                log.debug("Fallo actualizando el tooltip", exc_info=True)

    # ------------------------------------------------------------------ acciones
    def open_panel(self, *_: Any) -> None:
        webbrowser.open(self.controller.panel_url())

    def show_pairing(self, *_: Any) -> None:
        webbrowser.open(self.controller.panel_url() + "pair.html")

    def connect_usb(self, *_: Any) -> None:
        def task() -> None:
            st = self.state
            result = connect_usb(self.controller.port, st.settings.adb_path if st else None)
            self.notify(result.message, "Conexión USB" if result.ok else "Conexión USB: error")

        self._in_background(task)

    def toggle_wifi(self, *_: Any) -> None:
        st = self.state
        if st is None:
            return
        new_mode = "usb" if st.mode == "wifi" else "wifi"
        if new_mode == "wifi" and not winui.ask(
            "Se activará el modo WiFi: PhoneDeck escuchará en tu red local y los celulares "
            "necesitarán el PIN para conectarse.\n\nWindows puede pedirte permiso en el "
            "firewall: permite solo 'Redes privadas'.\n\n¿Continuar?",
            "Activar modo WiFi",
        ):
            return

        def task() -> None:
            st.settings_store.update(mode=new_mode)
            self.controller.restart(mode=new_mode)
            if new_mode == "wifi":
                pin = self.controller.state.settings.pin if self.controller.state else "?"
                self.notify(f"Modo WiFi activo. PIN: {pin}")
                self.show_pairing()
            else:
                self.notify("Modo USB activo: solo conexiones por cable / esta PC")

        self._in_background(task)

    def toggle_remote_edit(self, *_: Any) -> None:
        st = self.state
        if st is None:
            return
        enable = not st.settings.allow_remote_edit
        if enable and not winui.ask(
            "Los celulares emparejados por WiFi podrán modificar botones, incluidos botones "
            "que abran programas en esta PC.\n\nActívalo solo en una red de confianza y "
            "desactívalo al terminar de editar.\n\n¿Permitir la edición por WiFi?",
            "Permitir edición remota",
            warning=True,
        ):
            return
        st.settings_store.update(allow_remote_edit=enable)
        self.notify("Edición por WiFi " + ("permitida" if enable else "desactivada"))
        self.refresh()

    def new_pin(self, *_: Any) -> None:
        st = self.state
        if st is None:
            return
        pin = st.settings_store.regenerate_pin()
        self.notify(f"Nuevo PIN: {pin} (los celulares ya emparejados siguen conectados)")

    def revoke_all(self, *_: Any) -> None:
        st = self.state
        if st is None:
            return
        if not winui.ask(
            "Todos los celulares emparejados por WiFi tendrán que volver a introducir el PIN. "
            "¿Continuar?",
            "Desconectar dispositivos",
            warning=True,
        ):
            return
        st.settings_store.revoke_all_devices()
        st.settings_store.regenerate_pin()
        try:
            st.run_threadsafe(st.hub.close_all())
        except Exception:
            log.debug("No se pudieron cerrar los WebSockets", exc_info=True)
        self.notify("Dispositivos desconectados. Se generó un PIN nuevo.")

    def toggle_autostart(self, *_: Any) -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError as exc:
            self.notify(f"No se pudo cambiar el inicio automático: {exc}")
        self.refresh()

    def open_data_dir(self, *_: Any) -> None:
        _open_path(self.data_dir)

    def open_log(self, *_: Any) -> None:
        _open_path(self.log_file)

    def quit(self, *_: Any) -> None:
        self._stop.set()
        if self.icon is not None:
            self.icon.stop()

    # ---------------------------------------------------------------------- menú
    def _current_state(self) -> Any:
        return self.state

    def build_menu(self) -> Any:
        import pystray

        item = pystray.MenuItem
        st = self._current_state

        return pystray.Menu(
            item(lambda _i: self.tooltip(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Abrir panel", self.open_panel, default=True),
            item("Mostrar QR / PIN", self.show_pairing),
            item("Conectar celular por USB", self.connect_usb),
            pystray.Menu.SEPARATOR,
            item(
                "Modo WiFi", self.toggle_wifi, checked=lambda _i: bool(st() and st().mode == "wifi")
            ),
            item(
                "Permitir edición por WiFi",
                self.toggle_remote_edit,
                checked=lambda _i: bool(st() and st().settings.allow_remote_edit),
            ),
            item("Nuevo PIN", self.new_pin),
            item("Desconectar todos los dispositivos", self.revoke_all),
            pystray.Menu.SEPARATOR,
            item(
                "Iniciar con Windows",
                self.toggle_autostart,
                checked=lambda _i: autostart.is_enabled(),
                enabled=lambda _i: autostart.is_supported(),
            ),
            item("Abrir carpeta de configuración", self.open_data_dir),
            item("Ver registro (log)", self.open_log),
            pystray.Menu.SEPARATOR,
            item("Salir", self.quit),
        )

    def run(self) -> None:
        """Bloquea hasta que el usuario elige "Salir"."""
        import pystray

        self.icon = pystray.Icon("PhoneDeck", load_icon_image(), self.tooltip(), self.build_menu())
        threading.Thread(target=self._tooltip_loop, daemon=True).start()

        def setup(icon: Any) -> None:
            icon.visible = True
            self.notify(
                "PhoneDeck está en marcha. Haz clic derecho en este icono para ver opciones."
            )

        self.icon.run(setup=setup)


def run_with_tray(controller: ServerController, data_dir: Path, log_file: Path) -> int:
    """Arranca servidor + bandeja. Devuelve el código de salida."""
    if not winui.acquire_single_instance():
        winui.info("PhoneDeck ya está abierto (mira el icono junto al reloj).\nSe abrirá el panel.")
        webbrowser.open(f"http://127.0.0.1:{controller.options.port or 8765}/")
        return 0
    try:
        controller.start()
    except PortInUseError as exc:
        winui.error(f"{exc}\n\nCierra el otro programa o cambia el puerto en settings.json.")
        return 2
    except ServerStartError as exc:
        winui.error(f"{exc}\n\nRegistro: {log_file}")
        return 1
    autostart.refresh_path()
    try:
        TrayApp(controller, data_dir, log_file).run()
    finally:
        controller.stop()
    return 0
