"""Genera ``requirements/build.lock``: dependencias fijadas con versión y hash SHA-256.

Usa el resolutor de pip en modo ``--dry-run --report`` (no instala nada) y escribe una
línea ``paquete==versión --hash=sha256:...`` por cada paquete del árbol completo.
``build.bat`` instala con ``--require-hashes``: si un archivo de PyPI cambiara, la
instalación fallaría en vez de meter código distinto en el .exe.

Debe ejecutarse con el mismo Python que se usará para compilar (Windows x64, 3.13),
porque el hash corresponde al wheel concreto de esa plataforma.

Uso:  python scripts/lock_deps.py
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "requirements" / "build.in"
TARGET = ROOT / "requirements" / "build.lock"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--quiet",
                "--disable-pip-version-check",
                "--report",
                str(report_path),
                "-r",
                str(SOURCE),
            ],
            check=True,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))

    lines = []
    for entry in report["install"]:
        name = entry["metadata"]["name"]
        version = entry["metadata"]["version"]
        hashes = entry.get("download_info", {}).get("archive_info", {}).get("hashes", {})
        sha = hashes.get("sha256")
        if not sha:
            raise SystemExit(f"Sin hash sha256 para {name} {version}")
        lines.append(f"{name}=={version} \\\n    --hash=sha256:{sha}")
    lines.sort(key=str.lower)

    header = (
        "# GENERADO por scripts/lock_deps.py a partir de requirements/build.in. NO EDITAR.\n"
        f"# Plataforma: {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}\n"
        "# Instalar con: pip install --require-hashes --no-deps -r requirements/build.lock\n"
    )
    TARGET.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)}: {len(lines)} paquetes fijados con hash")


if __name__ == "__main__":
    main()
