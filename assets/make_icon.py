#!/usr/bin/env python3
"""Render assets/icon.svg into assets/icon.icns (and a 1024 PNG preview).

Uses PyMuPDF to rasterise the SVG, Pillow to resize, and the macOS
`iconutil` to pack the .iconset into a .icns. Run with the project venv:

    .venv/bin/python assets/make_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

HERE = Path(__file__).resolve().parent
SVG = HERE / "icon.svg"
ICONSET = HERE / "icon.iconset"
ICNS = HERE / "icon.icns"
PREVIEW = HERE / "icon-1024.png"

# (filename, pixel size) pairs iconutil expects
SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def render_master(px: int = 1024) -> Image.Image:
    """Rasterise the SVG at `px` square with an alpha channel."""
    doc = fitz.open(str(SVG))
    page = doc[0]
    scale = px / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
    return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)


def main() -> int:
    if not SVG.exists():
        print(f"missing {SVG}", file=sys.stderr)
        return 1

    master = render_master(1024)
    master.save(PREVIEW)
    print(f"wrote {PREVIEW.relative_to(HERE.parent)}")

    ICONSET.mkdir(exist_ok=True)
    for name, size in SIZES:
        img = master.resize((size, size), Image.LANCZOS)
        img.save(ICONSET / name)
    print(f"wrote {len(SIZES)} pngs to {ICONSET.relative_to(HERE.parent)}")

    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
        check=True,
    )
    shutil.rmtree(ICONSET)
    print(f"wrote {ICNS.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
