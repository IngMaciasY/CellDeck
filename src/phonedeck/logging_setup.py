"""Configuración de logs: archivo rotativo + consola (si existe)."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(log_dir: Path, debug: bool = False) -> Path:
    """Configura el logger raíz. Devuelve la ruta del archivo de log.

    En el .exe sin consola ``sys.stderr`` es ``None``: entonces solo se escribe a archivo.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "phonedeck.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(FORMAT)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)

    # Librerías ruidosas
    for noisy in ("comtypes", "PIL", "asyncio", "websockets", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_file
