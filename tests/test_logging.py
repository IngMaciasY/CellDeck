"""Los tokens nunca deben acabar en el archivo de log."""

from __future__ import annotations

import logging
from pathlib import Path

from phonedeck.logging_setup import setup_logging


def test_tokens_are_redacted(tmp_path: Path) -> None:
    log_file = setup_logging(tmp_path)
    try:
        logger = logging.getLogger("uvicorn.error")
        token = "eyJ2IjoxfQ.AbC-123_xyz"
        # Igual que el mensaje real de uvicorn (con argumentos %s)
        logger.info('%s - "WebSocket %s" [accepted]', "127.0.0.1:5000", f"/ws?token={token}")
        logger.info("GET /api/media/artwork?h=abc&token=%s", token)
        logger.info("cabecera x-phonedeck-token: %s", token)
        for handler in logging.getLogger().handlers:
            handler.flush()
        text = log_file.read_text(encoding="utf-8")
        assert token not in text
        assert text.count("token=***") == 2
        assert "x-phonedeck-token: ***" in text
        assert "h=abc" in text  # el resto del mensaje se conserva
    finally:
        for handler in list(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)
