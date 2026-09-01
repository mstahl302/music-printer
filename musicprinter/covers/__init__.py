"""Cover-sheet detection.

`detect_cover(path, mode, threshold)` is the entry point. Modes:

- ``"none"``   — never remove anything.
- ``"always"`` — remove page 1 (unless the file is a single page).
- ``"smart"``  — run every detector in :data:`REGISTRY`; return the
  highest-confidence match at or above ``threshold``.

Add a vendor by writing a detector class (see ``musicnotes.py``) and
appending it to :data:`REGISTRY`.
"""

from __future__ import annotations

import pymupdf

from .base import CoverDetector, CoverMatch
from .musicnotes import MusicnotesCoverDetector

__all__ = ["CoverDetector", "CoverMatch", "REGISTRY", "DEFAULT_THRESHOLD", "detect_cover"]

REGISTRY: list[CoverDetector] = [MusicnotesCoverDetector()]

DEFAULT_THRESHOLD = 0.70


def detect_cover(path, mode: str, *, threshold: float = DEFAULT_THRESHOLD) -> CoverMatch | None:
    if mode == "none":
        return None
    if mode not in ("always", "smart"):
        raise ValueError(f"unknown strip mode {mode!r}")

    doc = pymupdf.open(path)
    try:
        if mode == "always":
            if doc.page_count <= 1:
                return None
            return CoverMatch("manual", (0,), 1.0, "always-remove mode")

        best: CoverMatch | None = None
        for detector in REGISTRY:
            match = detector.detect(doc)
            if match is None or match.confidence < threshold:
                continue
            if best is None or match.confidence > best.confidence:
                best = match
        return best
    finally:
        doc.close()
