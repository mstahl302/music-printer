"""Turn a source PDF + strip mode into a concrete print plan, and build the
per-pass temp PDFs. No UI, no threads, no printing — main.py drives the
actual submit / track / flip-gate state machine using musicprinter.printing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import covers, pdfio
from .covers.base import CoverMatch
from .duplex import PrintPlan, plan_passes


@dataclass(frozen=True)
class Plan:
    source_path: Path
    n_source_pages: int
    strip_mode: str
    cover: CoverMatch | None      # the match being applied, or None
    n_effective: int
    passes: PrintPlan

    @property
    def cover_removed(self) -> int:
        return len(self.cover.pages) if self.cover else 0

    @property
    def sheets_to_prepare(self) -> int:
        return self.passes.sheets_per_pass

    @property
    def thumbnail_source_index0(self) -> int:
        """Source page index (0-based) that becomes effective page 1."""
        return self.cover_removed

    def cover_summary(self) -> str:
        mode, m = self.strip_mode, self.cover
        if mode == "none":
            return "Cover removal off"
        if mode == "always":
            return ("Forced — first page removed" if m
                    else "Forced — file is 1 page, nothing removed")
        # smart
        if m is None:
            return f"Smart — no cover detected, all {self.n_source_pages} pages kept"
        if m.confidence >= 0.95:
            return f"Smart — {m.detector} cover detected ({m.confidence:.2f}), page 1 removed"
        return f"Smart — likely cover ({m.confidence:.2f}), page 1 removed"


def build_plan(source_path, strip_mode: str, *, threshold: float) -> Plan:
    """Inspect the PDF, run cover detection, and compute the two-pass plan.

    Raises :class:`pdfio.PdfError` for an unreadable, encrypted, or empty PDF.
    """
    source_path = Path(source_path)
    n_pages, needs_password = pdfio.inspect(source_path)
    if needs_password:
        raise pdfio.PdfError("This PDF is password-protected. Music Printer can't open it.")
    if n_pages == 0:
        raise pdfio.PdfError("This PDF has no pages.")

    match = covers.detect_cover(source_path, strip_mode, threshold=threshold)
    removed = len(match.pages) if match else 0
    if removed >= n_pages:          # never strip the whole document
        match, removed = None, 0

    n_effective = n_pages - removed
    return Plan(source_path, n_pages, strip_mode, match, n_effective, plan_passes(n_effective))


def _to_source_pages(effective_pages, removed: int) -> list[int]:
    return [p + removed for p in effective_pages]


def build_pass_pdf(plan: Plan, which: str, out_dir) -> Path:
    """Build the temp PDF for a pass. ``which`` in {"even", "odd", "single"}."""
    removed = plan.cover_removed
    if which == "even":
        pages = _to_source_pages(plan.passes.even_pages, removed)
        return pdfio.build_subset(plan.source_path, pages,
                                  pdfio.pass_pdf_path(out_dir, "pass1"),
                                  append_blank=plan.passes.pad_blank)
    if which in ("odd", "single"):
        pages = _to_source_pages(plan.passes.odd_pages, removed)
        tag = "single" if which == "single" else "pass2"
        return pdfio.build_subset(plan.source_path, pages,
                                  pdfio.pass_pdf_path(out_dir, tag))
    raise ValueError(f"unknown pass {which!r}")
