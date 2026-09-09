#!/usr/bin/env python3
"""Genera de forma reproducible el ZIP instalable del addon para Kodi.

Usa el utilitario `zip` del sistema (Info-ZIP). Los ZIP creados solo con
zipfile de Python provocan en varios Kodi:
  - Failed to unpack archive
  - Unable to load .../addon.xml, Line 0
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDON = ROOT / "plugin.video.launcherm3u"
ADDON_ID = "plugin.video.launcherm3u"
EXCLUDED_DIRS = {"__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _addon_version() -> str:
    addon_xml = (ADDON / "addon.xml").read_text(encoding="utf-8")
    match = re.search(r"<addon\b[^>]*\bversion=\"([^\"]+)\"", addon_xml)
    if not match:
        raise RuntimeError("No se encontró la versión del addon")
    return match.group(1)


def _copy_addon_tree(dest_root: Path) -> None:
    dest_addon = dest_root / ADDON_ID
    for path in sorted(ADDON.rglob("*")):
        relative = path.relative_to(ADDON)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_dir():
            (dest_addon / relative).mkdir(parents=True, exist_ok=True)
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        target = dest_addon / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main() -> Path:
    if not shutil.which("zip"):
        raise RuntimeError("Se necesita el comando 'zip' (Info-ZIP) en el PATH")

    version = _addon_version()
    # Convención Kodi: ADDONID-VERSION.zip
    target = ROOT / f"{ADDON_ID}-{version}.zip"
    alias = ROOT / f"launcherm3u-{version}.zip"

    with tempfile.TemporaryDirectory(prefix="launcherm3u-zip-") as tmp:
        tmp_path = Path(tmp)
        _copy_addon_tree(tmp_path)
        staging_zip = tmp_path / target.name
        # -r recursivo, -9 compresión, -X sin metadatos extra (uid/gid/atime)
        # que a veces confunden al instalador de Kodi.
        subprocess.run(
            ["zip", "-r", "-9", "-X", str(staging_zip), ADDON_ID],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        shutil.copy2(staging_zip, target)

    alias.write_bytes(target.read_bytes())
    print(target)
    print(alias)
    return target


if __name__ == "__main__":
    main()
