"""Versionado de archivos estáticos para poder cachearlos de forma permanente.

Al arrancar se calcula un hash del contenido de ``web/``. Las páginas HTML se sirven
con ``?v=<hash>`` añadido a sus scripts, hojas de estilo e imágenes locales; esas URLs
se cachean como ``immutable`` (el navegador no vuelve a preguntar). Si cambia cualquier
archivo (nueva versión de CellDeck), cambia el hash y por tanto todas las URLs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Referencias locales a versionar dentro del HTML.
_ASSET_REF = re.compile(r'(\s(?:src|href)=")((?:js|css|icons|media)/[^"?#]+)(")')

IMMUTABLE = "public, max-age=31536000, immutable"


def compute_asset_version(web_dir: Path) -> str:
    """Hash corto del contenido de ``web_dir`` (nombres + bytes de cada archivo)."""
    digest = hashlib.sha256()
    for path in sorted(p for p in web_dir.rglob("*") if p.is_file()):
        digest.update(path.relative_to(web_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def render_html(html: str, version: str) -> str:
    """Añade ``?v=`` a los recursos locales y ``data-v`` a <html> (para cargas diferidas)."""
    html = _ASSET_REF.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={version}{m.group(3)}", html)
    return html.replace("<html ", f'<html data-v="{version}" ', 1)
