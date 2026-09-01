"""Musicnotes.com cover-sheet detector.

Signals and their measured discrimination are documented in
docs/cover_signals.md §3. In short, page 1 is a cover when it carries no
engraved music (A) and Musicnotes cover boilerplate text (B).
"""

from __future__ import annotations

import pymupdf

from .base import (
    CoverMatch,
    norm,
    page_has_full_page_image,
    staff_line_count,
    vector_draw_count,
)

# Phrases seen on 6/6 sample covers and 0/6 sample music page-1s.
# The bare string "musicnotes.com" is deliberately NOT here — it appears
# on nearly every page of nearly every file.
MUSICNOTES_COVER_PHRASES = (
    "published under license from",
    "purchasers of this musical file are entitled to use it for their "
    "personal enjoyment and musical fulfillment",
    "unauthorized uses are infringements of the copyright laws of the united states",
)


class MusicnotesCoverDetector:
    name = "musicnotes"

    def detect(self, doc: "pymupdf.Document") -> CoverMatch | None:
        if doc.page_count == 0:
            return None
        page = doc[0]
        text = norm(page.get_text("text"))

        no_music = staff_line_count(page) == 0 and vector_draw_count(page) <= 2
        has_boilerplate = any(p in text for p in MUSICNOTES_COVER_PHRASES)

        if no_music and has_boilerplate:
            return CoverMatch(
                self.name, (0,), 0.97,
                "page 1 has no engraved music and Musicnotes cover boilerplate",
            )
        if no_music and len(text) > 150 and not page_has_full_page_image(page):
            return CoverMatch(
                self.name, (0,), 0.75,
                "page 1 has no engraved music and reads as a title/text page",
            )
        if has_boilerplate:
            return CoverMatch(
                self.name, (0,), 0.35,
                "cover boilerplate found, but page 1 also appears to contain music",
            )
        return None
