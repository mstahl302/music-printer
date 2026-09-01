"""PDF I/O for Music Printer: inspection, thumbnail rendering, and building
the per-pass subset PDFs.

pymupdf does the reading / rendering / structural analysis; pikepdf writes
the subset files (faithful page copying + blank-page insertion).
"""

from __future__ import annotations

import os
from pathlib import Path

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


def build_pages(refs, out_path, *, default_size=(612.0, 792.0)) -> Path:
    """Write ``out_path`` from a mixed list of pages across several sources.

    ``refs`` is a list of ``(src_path, page_1indexed)`` for a real page, or
    ``(None, None)`` for a blank. Blanks take the media box of the most
    recent real page (fallback: ``default_size``). Each source is opened
    once.
    """
    out_path = Path(out_path)
    dst = pikepdf.new()
    open_src: dict[str, pikepdf.Pdf] = {}
    last_wh = default_size
    try:
        for src_path, pageno in refs:
            if src_path is None:
                dst.add_blank_page(page_size=last_wh)
                continue
            key = str(src_path)
            src = open_src.get(key)
            if src is None:
                src = open_src[key] = pikepdf.open(src_path)
            page = src.pages[pageno - 1]
            dst.pages.append(page)
            box = page.MediaBox
            last_wh = (float(box[2]) - float(box[0]), float(box[3]) - float(box[1]))
        dst.save(out_path)
        return out_path
    finally:
        for src in open_src.values():
            src.close()
        dst.close()


def pass_pdf_path(out_dir, tag: str) -> Path:
    """Deterministic per-process temp name, e.g. ``music-printer-1234-pass1.pdf``."""
    return Path(out_dir) / f"music-printer-{os.getpid()}-{tag}.pdf"
