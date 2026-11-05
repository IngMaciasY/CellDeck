"""Punto de entrada: ``python -m phonedeck`` o ``PhoneDeck.exe``.

Por defecto arranca con icono en la bandeja. ``--no-tray`` ejecuta solo el servidor
(útil para desarrollo, CI o sistemas sin bandeja).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from phonedeck import __version__, paths
from phonedeck.logging_setup import setup_logging

log = logging.getLogger("phonedeck")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="phonedeck", description="Servidor de PhoneDeck")
    parser.add_argument("--data-dir", type=Path, default=None, help="Carpeta de config y logs")
    parser.add_argument(
        "--mode", choices=["usb", "wifi"], default=None, help="Fuerza el modo de red (no se guarda)"
    )
    parser.add_argument("--port", type=int, default=None, help="Puerto (por defecto 8765)")
    parser.add_argument(
        "--fake", action="store_true", help="Backend simulado: no toca Windows (desarrollo)"
    )
    parser.add_argument("--no-tray", action="store_true", help="Sin icono en la bandeja")
    parser.add_argument("--debug", action="store_true", help="Logs detallados")
    parser.add_argument("--version", action="version", version=f"PhoneDeck {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir: Path = args.data_dir or paths.app_data_dir()
    log_file = setup_logging(data_dir / "logs", debug=args.debug)
    log.info("PhoneDeck %s · datos en %s · log en %s", __version__, data_dir, log_file)

    from phonedeck.app import LaunchOptions, PortInUseError, serve

    options = LaunchOptions(data_dir=data_dir, fake=args.fake, mode=args.mode, port=args.port)
    try:
        if args.no_tray:
            serve(options)
            return 0
        from phonedeck.app import ServerController
        from phonedeck.tray import run_with_tray

        return run_with_tray(ServerController(options), data_dir, log_file)
    except PortInUseError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.exception("Error fatal")
        if not args.no_tray:
            from phonedeck import winui

            winui.error(f"Error inesperado: {exc}\n\nRegistro: {log_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
