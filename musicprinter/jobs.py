"""Turn an ordered list of PDFs + strip mode into a concrete print plan,
and build the per-pass mega-PDFs. No UI, no threads, no printing — main.py
drives the submit / track / flip-gate state machine.

The everyday case is a list of one file; nothing about it is special.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import covers, pdfio
from .covers.base import CoverMatch
from .duplex import SetLayout, plan_set


@dataclass(frozen=True)
class FileEntry:
    path: Path
    n_source: int                 # 0 when the file can't be opened
    cover: CoverMatch | None
    n_effective: int
    error: str | None = None      # human-readable reason it can't be printed

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def cover_removed(self) -> int:
        return len(self.cover.pages) if self.cover else 0


@dataclass(frozen=True)
class SetPlan:
    entries: tuple[FileEntry, ...]   # every file the user added, in order
    strip_mode: str
    layout: SetLayout | None         # None while any file has an error

    @property
    def ok_entries(self) -> list[FileEntry]:
        return [e for e in self.entries if e.ok]

    @property
    def has_errors(self) -> bool:
        return any(not e.ok for e in self.entries)

    @property
    def n_files(self) -> int:
        return len(self.ok_entries)

    @property
    def sheets_to_prepare(self) -> int:
        return self.layout.sheets_per_pass if self.layout else 0

    @property
    def single_pass(self) -> bool:
        return bool(self.layout and self.layout.single_pass)

    @property
    def run_title(self) -> str:
        ok = self.ok_entries
        if len(ok) == 1:
            return f"Printing — {ok[0].path.name}"
        return f"Printing — {len(ok)} songs"


def _inspect_one(path: Path, strip_mode: str, threshold: float) -> FileEntry:
    try:
        n_src, needs_pw = pdfio.inspect(path)
    except pdfio.PdfError:
        return FileEntry(path, 0, None, 0, error="Can't open this PDF")
    if needs_pw:
        return FileEntry(path, 0, None, 0, error="This PDF is password-protected")
    if n_src == 0:
        return FileEntry(path, 0, None, 0, error="This PDF has no pages")

    match = covers.detect_cover(path, strip_mode, threshold=threshold)
    removed = len(match.pages) if match else 0
    if removed >= n_src:                 # never strip the whole document
        match, removed = None, 0
    return FileEntry(path, n_src, match, n_src - removed)


def build_plan(files, strip_mode: str, *, threshold: float) -> SetPlan:
    """Inspect every file, run cover detection, and (if all files are OK) plan
    the combined two-pass job."""
    entries = tuple(_inspect_one(Path(f), strip_mode, threshold) for f in files)
    ok = [e for e in entries if e.ok]
    layout = plan_set([e.n_effective for e in ok]) if ok and all(e.ok for e in entries) else None
    return SetPlan(entries, strip_mode, layout)


def _pass_refs(plan: SetPlan, which: str):
    """(src_path, page_1indexed) | (None, None) for each page of the pass."""
    assert plan.layout is not None
    ok = plan.ok_entries
    refs = plan.layout.odd_refs() if which in ("odd", "single") else plan.layout.even_refs()
    out = []
    for file_idx, eff_page in refs:
        if eff_page is None:
            out.append((None, None))
        else:
            e = ok[file_idx]
            out.append((e.path, eff_page + e.cover_removed))
    return out


def build_pass_pdf(plan: SetPlan, which: str, out_dir) -> Path:
    """Build a mega-PDF for a pass. ``which`` in {"even", "odd", "single"}."""
    tag = {"even": "pass1", "odd": "pass2", "single": "single"}.get(which)
    if tag is None:
        raise ValueError(f"unknown pass {which!r}")
    return pdfio.build_pages(_pass_refs(plan, which), pdfio.pass_pdf_path(out_dir, tag))
