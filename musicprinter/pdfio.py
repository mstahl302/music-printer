"""PDF I/O for Music Printer: inspection, thumbnail rendering, and building
the per-pass subset PDFs.

pymupdf does the reading / rendering / structural analysis; pikepdf writes
the subset files (faithful page copying + blank-page insertion).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pikepdf
import pymupdf


class PdfError(Exception):
    """Raised for a PDF we can't or won't process (unreadable, encrypted, empty)."""


def inspect(path) -> tuple[int, bool]:
    """Return ``(page_count, needs_password)``. Raises :class:`PdfError` if unreadable."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # pymupdf raises various types
        raise PdfError(f"Could not open PDF: {exc}") from exc
    try:
        return doc.page_count, bool(doc.needs_pass)
    finally:
        doc.close()


def render_thumbnail_png(path, page_index0: int, *, max_px: int = 360) -> bytes:
    """Render one page to PNG bytes, longest side ``max_px``."""
    doc = pymupdf.open(path)
    try:
        page = doc[page_index0]
        longest = max(page.rect.width, page.rect.height) or 1.0
        scale = max_px / longest
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def build_subset(src_path, pages_1indexed: Iterable[int], out_path,
                 *, append_blank: bool = False) -> Path:
    """Write ``out_path`` containing ``pages_1indexed`` from ``src_path`` in order.

    If ``append_blank`` is set, add one empty page matching the last
    copied page's box (fallback: source page 1).
    """
    pages_1indexed = list(pages_1indexed)
    src = pikepdf.open(src_path)
    dst = pikepdf.new()
    try:
        for p in pages_1indexed:
            dst.pages.append(src.pages[p - 1])

        if append_blank:
            ref = dst.pages[-1] if len(dst.pages) else src.pages[0]
            box = ref.MediaBox
            w = float(box[2]) - float(box[0])
            h = float(box[3]) - float(box[1])
            dst.add_blank_page(page_size=(w, h))

        out_path = Path(out_path)
        dst.save(out_path)
        return out_path
    finally:
        src.close()
        dst.close()


def pass_pdf_path(out_dir, tag: str) -> Path:
    """Deterministic per-process temp name, e.g. ``music-printer-1234-pass1.pdf``."""
    return Path(out_dir) / f"music-printer-{os.getpid()}-{tag}.pdf"
