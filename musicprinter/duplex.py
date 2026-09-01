"""Pure page-planning for the two-pass simplex-duplex workflow.

No I/O. Given effective page counts (after any cover removal), work out
which pages go in the EVEN pass, which in the ODD pass, and whether a
blank pad sheet is needed.

:func:`plan_passes` handles a single document; :func:`plan_set` handles an
ordered list of documents printed as one job (docs/spec_batch_printing.md).
See docs/specification.md §7.2 and Appendix A.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

# A page in one of the mega-PDFs: (file index, effective page within that
# file). ``page is None`` means an inserted blank belonging to that file.
GlobalRef = tuple[int, "int | None"]


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


@dataclass(frozen=True)
class SetLayout:
    """An ordered list of documents planned as one two-pass job.

    Every file except the last is padded to an even effective length so the
    next file starts on a sheet front; the last file is left as-is and any
    resulting odd total is absorbed by :class:`PrintPlan`'s trailing blank.
    For a list of one this is exactly :func:`plan_passes`.
    """

    effective_lengths: tuple[int, ...]
    padded_lengths: tuple[int, ...]
    starts: tuple[int, ...]        # 1-based global page each file begins at
    total: int
    passes: PrintPlan

    @property
    def n_files(self) -> int:
        return len(self.effective_lengths)

    @property
    def sheets_per_pass(self) -> int:
        return self.passes.sheets_per_pass

    @property
    def single_pass(self) -> bool:
        return self.passes.single_pass

    def file_sheets(self, i: int) -> int:
        """Sheets that carry file ``i``'s music (ceil of its effective pages)."""
        return math.ceil(self.effective_lengths[i] / 2)

    def _resolve(self, global_page: int) -> GlobalRef:
        for i, start in enumerate(self.starts):
            span = self.padded_lengths[i]
            if start <= global_page < start + span:
                eff = global_page - start + 1
                return (i, eff if eff <= self.effective_lengths[i] else None)
        raise IndexError(global_page)

    def even_refs(self) -> list[GlobalRef]:
        refs = [self._resolve(g) for g in self.passes.even_pages]
        if self.passes.pad_blank:
            refs.append((self.n_files - 1, None))   # trailing blank on the last file
        return refs

    def odd_refs(self) -> list[GlobalRef]:
        return [self._resolve(g) for g in self.passes.odd_pages]


def plan_set(effective_lengths: Sequence[int]) -> SetLayout:
    """Plan an ordered list of documents as one job. ``effective_lengths`` is
    each document's page count after cover removal."""
    lengths = [int(n) for n in effective_lengths]
    if not lengths:
        raise ValueError("plan_set needs at least one document")
    if any(n < 0 for n in lengths):
        raise ValueError(f"effective lengths must be >= 0: {lengths}")

    last = len(lengths) - 1
    padded = [n + (n % 2) if i != last else n for i, n in enumerate(lengths)]

    starts, acc = [], 1
    for span in padded:
        starts.append(acc)
        acc += span
    total = acc - 1

    return SetLayout(tuple(lengths), tuple(padded), tuple(starts), total, plan_passes(total))
