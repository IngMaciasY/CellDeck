"""Configuración de logs: archivo rotativo + consola (si existe)."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Tokens en URLs (/ws?token=..., /api/media/artwork?token=...) o en cabeceras, y el código de
# autorización con el que Spotify vuelve a /api/spotify/callback?code=...&state=...
_TOKEN_RE = re.compile(
    r"(token=|[?&]code=|[?&]state=|x-phonedeck-token[\"']?:\s*[\"']?)[A-Za-z0-9_\-.]+",
    re.IGNORECASE,
)


class RedactTokensFilter(logging.Filter):
    """Oculta los tokens de sesión antes de escribir el log.

    uvicorn registra la ruta completa de cada WebSocket (``/ws?token=...``): sin este
    filtro, cualquiera con acceso al archivo de log podría copiar un token válido.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _TOKEN_RE.sub(r"\1***", message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


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
    redact = RedactTokensFilter()
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redact)
    root.addHandler(file_handler)

    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        console.addFilter(redact)
        root.addHandler(console)

    # Librerías ruidosas
    for noisy in ("comtypes", "PIL", "asyncio", "websockets", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_file
