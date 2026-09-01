"""Pure page-planning for the two-pass simplex-duplex workflow.

No I/O. Given a count of effective pages (after any cover removal), work
out which pages go in the EVEN pass, which in the ODD pass, and whether a
blank pad sheet is needed. See docs/specification.md §7.2 and Appendix A.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrintPlan:
    n_pages: int                  # effective page count
    even_pages: tuple[int, ...]   # effective page numbers, ascending
    odd_pages: tuple[int, ...]    # effective page numbers, ascending
    pad_blank: bool               # append one blank to the EVEN pass
    single_pass: bool             # N <= 1 (or EVEN empty): print directly, no flip

    @property
    def sheets_per_pass(self) -> int:
        """Sheets of paper the user must load (same for both passes)."""
        even = len(self.even_pages) + (1 if self.pad_blank else 0)
        return max(even, len(self.odd_pages))


def plan_passes(n_pages: int) -> PrintPlan:
    """Build the :class:`PrintPlan` for ``n_pages`` effective pages."""
    if n_pages < 0:
        raise ValueError(f"n_pages must be >= 0, got {n_pages}")

    even = tuple(range(2, n_pages + 1, 2))
    odd = tuple(range(1, n_pages + 1, 2))

    if n_pages <= 1 or not even:
        # single page (or nothing): print the ODD set directly, no flip
        return PrintPlan(n_pages, (), odd, pad_blank=False, single_pass=True)

    return PrintPlan(
        n_pages, even, odd,
        pad_blank=(n_pages % 2 == 1),
        single_pass=False,
    )
