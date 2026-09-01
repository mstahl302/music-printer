"""Shared types and page-structure helpers for cover-sheet detection.

See docs/cover_signals.md for what these measurements mean and why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import pymupdf

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class CoverMatch:
    detector: str            # e.g. "musicnotes", or "manual" for always-remove
    pages: tuple[int, ...]   # 0-indexed source pages to remove; v1 is always (0,)
    confidence: float        # 0.0 - 1.0
    reason: str              # short, shown in the plan preview


class CoverDetector(Protocol):
    name: str

    def detect(self, doc: "pymupdf.Document") -> CoverMatch | None:
        ...


def norm(text: str) -> str:
    """Lower-case, collapse all whitespace to single spaces, strip ends."""
    return _WS.sub(" ", text).strip().lower()


def staff_line_count(page: "pymupdf.Page") -> int:
    """Long, near-horizontal vector segments — a proxy for engraved staves."""
    n = 0
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 1.5 and abs(p1.x - p2.x) > 120:
                    n += 1
    return n


def vector_draw_count(page: "pymupdf.Page") -> int:
    return len(page.get_drawings())


def page_has_full_page_image(page: "pymupdf.Page", frac: float = 0.5) -> bool:
    """True if any single image covers >= ``frac`` of the page (scanned music)."""
    page_area = abs(page.rect.width * page.rect.height)
    if page_area <= 0:
        return False
    for info in page.get_image_info():
        bbox = info.get("bbox")
        if not bbox:
            continue
        r = pymupdf.Rect(bbox)
        if abs(r.width * r.height) >= frac * page_area:
            return True
    return False
