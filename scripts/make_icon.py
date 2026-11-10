"""Genera el icono de CellDeck: ``assets/celldeck.ico`` y los PNG de ``web/icons/``.

Dibujado con Pillow (sin archivos de terceros). Uso:  python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
TOP = (79, 140, 255)  # #4f8cff
BOTTOM = (43, 95, 217)  # #2b5fd9
KEY = (255, 255, 255, 235)
KEY_ACCENT = (29, 185, 84, 255)  # verde "play"


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    """Icono cuadrado. ``maskable`` deja margen de seguridad para iconos adaptativos."""
    scale = 4  # supermuestreo para bordes suaves
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Fondo con degradado vertical
    grad = Image.new("RGBA", (s, s))
    gdraw = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        color = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        gdraw.line([(0, y), (s, y)], fill=(*color, 255))
    mask = Image.new("L", (s, s), 0)
    radius = 0 if maskable else int(s * 0.22)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # Rejilla 3x2 de "teclas"
    draw = ImageDraw.Draw(img)
    pad = s * (0.24 if maskable else 0.17)
    gap = s * 0.06
    cols, rows = 3, 2
    key_w = (s - 2 * pad - (cols - 1) * gap) / cols
    key_h = key_w
    top = (s - rows * key_h - (rows - 1) * gap) / 2
    for r in range(rows):
        for c in range(cols):
            x0 = pad + c * (key_w + gap)
            y0 = top + r * (key_h + gap)
            fill = KEY_ACCENT if (r, c) == (0, 1) else KEY
            draw.rounded_rectangle([x0, y0, x0 + key_w, y0 + key_h], radius=key_w * 0.22, fill=fill)
            if (r, c) == (0, 1):  # triángulo de play
                cx, cy, h = x0 + key_w / 2, y0 + key_h / 2, key_h * 0.42
                draw.polygon(
                    [(cx - h * 0.4, cy - h / 2), (cx - h * 0.4, cy + h / 2), (cx + h * 0.5, cy)],
                    fill=(255, 255, 255, 255),
                )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icons = ROOT / "web" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_icon(size).save(icons / f"app-{size}.png", optimize=True)
    draw_icon(512, maskable=True).save(icons / "app-maskable-512.png", optimize=True)
    draw_icon(32).save(icons / "favicon-32.png", optimize=True)

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    big = draw_icon(256)
    big.save(
        assets / "celldeck.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    big.save(assets / "celldeck.png")
    print("Iconos generados en web/icons/ y assets/")


if __name__ == "__main__":
    main()
