"""Punto de entrada: ``python -m celldeck`` o ``CellDeck.exe``.

Por defecto arranca con icono en la bandeja. ``--no-tray`` ejecuta solo el servidor
(útil para desarrollo, CI o sistemas sin bandeja).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from celldeck import __version__, paths
from celldeck.logging_setup import setup_logging

log = logging.getLogger("celldeck")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="celldeck", description="Servidor de CellDeck")
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
    parser.add_argument("--version", action="version", version=f"CellDeck {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    migrated: Path | None = None
    if args.data_dir is None:
        try:
            migrated = paths.migrate_legacy_data_dir()
        except OSError as exc:  # sin permisos, disco lleno...: se arranca con datos nuevos
            print(f"No se pudieron copiar los datos de PhoneDeck: {exc}", file=sys.stderr)
    data_dir: Path = args.data_dir or paths.app_data_dir()
    log_file = setup_logging(data_dir / "logs", debug=args.debug)
    log.info("CellDeck %s · datos en %s · log en %s", __version__, data_dir, log_file)
    if migrated is not None:
        log.info("Datos copiados desde %s (nombre anterior del proyecto)", migrated)

    from celldeck.app import LaunchOptions, PortInUseError, serve

    options = LaunchOptions(data_dir=data_dir, fake=args.fake, mode=args.mode, port=args.port)
    try:
        if args.no_tray:
            serve(options)
            return 0
        from celldeck.app import ServerController
        from celldeck.tray import run_with_tray

        return run_with_tray(ServerController(options), data_dir, log_file)
    except PortInUseError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.exception("Error fatal")
        if not args.no_tray:
            from celldeck import winui

            winui.error(f"Error inesperado: {exc}\n\nRegistro: {log_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
