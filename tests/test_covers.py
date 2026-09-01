"""Cover detection + plan building, against synthetic PDFs.

Real Musicnotes files can't be committed; these fixtures reproduce the two
signals from docs/cover_signals.md: a text-only page 1 with the boilerplate
(cover) vs a page 1 full of staff lines (music).
"""

import pikepdf
import pymupdf
import pytest

from musicprinter import covers, jobs
from musicprinter.pdfio import PdfError

COVER_TEXT = (
    'From: "Test Show"\n'
    "A Test Song\n"
    "by\n"
    "A COMPOSER\n"
    "Published Under License From\n"
    "Some Publisher\n"
    "Copyright (c) 2020\n"
    "NOTICE: Purchasers of this musical file are entitled to use it for their "
    "personal enjoyment and musical fulfillment. However, any duplication, "
    "adaptation, arranging and/or transmission of this copyrighted music "
    "requires the written consent of the copyright owner(s). Unauthorized uses "
    "are infringements of the copyright laws of the United States and other "
    "countries.\n"
    "musicnotes.com\n"
    "Authorized for use by Test User\n"
)


def _add_cover_page(doc):
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(pymupdf.Rect(60, 60, 552, 732), COVER_TEXT, fontsize=11)


def _add_music_page(doc):
    page = doc.new_page(width=612, height=792)
    y = 100
    for _ in range(6):  # six 5-line staves
        for i in range(5):
            page.draw_line((72, y + i * 8), (540, y + i * 8))
        y += 90
    page.insert_text((72, 60), "q = 120   Verse")


def _write(path, *, cover: bool, music_pages: int):
    doc = pymupdf.open()
    if cover:
        _add_cover_page(doc)
    for _ in range(music_pages):
        _add_music_page(doc)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def cover_pdf(tmp_path):
    return _write(tmp_path / "with_cover.pdf", cover=True, music_pages=3)


@pytest.fixture
def plain_pdf(tmp_path):
    return _write(tmp_path / "no_cover.pdf", cover=False, music_pages=3)


# ---- detection ------------------------------------------------------

def test_smart_detects_cover(cover_pdf):
    m = covers.detect_cover(cover_pdf, "smart", threshold=0.70)
    assert m is not None and m.pages == (0,)
    assert m.confidence >= 0.95
    assert m.detector == "musicnotes"


def test_smart_keeps_plain_music(plain_pdf):
    assert covers.detect_cover(plain_pdf, "smart", threshold=0.70) is None


def test_none_mode_never_strips(cover_pdf):
    assert covers.detect_cover(cover_pdf, "none", threshold=0.70) is None


def test_always_mode_strips_first_page(plain_pdf):
    m = covers.detect_cover(plain_pdf, "always", threshold=0.70)
    assert m is not None and m.pages == (0,) and m.detector == "manual"


def test_always_mode_leaves_single_page_alone(tmp_path):
    one = _write(tmp_path / "one.pdf", cover=False, music_pages=1)
    assert covers.detect_cover(one, "always", threshold=0.70) is None


# ---- plan building (list of one) ---------------------------------

def test_build_plan_removes_cover_and_renumbers(cover_pdf):
    sp = jobs.build_plan([cover_pdf], "smart", threshold=0.70)
    e = sp.entries[0]
    assert e.n_source == 4 and e.cover_removed == 1 and e.n_effective == 3
    assert sp.layout.passes.even_pages == (2,)
    assert sp.layout.passes.odd_pages == (1, 3)
    assert sp.layout.passes.pad_blank is True
    assert sp.sheets_to_prepare == 2
    assert sp.n_files == 1 and not sp.has_errors


def test_build_plan_no_cover(plain_pdf):
    sp = jobs.build_plan([plain_pdf], "smart", threshold=0.70)
    assert sp.entries[0].cover_removed == 0
    assert sp.entries[0].n_effective == 3


def test_build_plan_flags_unopenable_file(tmp_path, plain_pdf):
    sp = jobs.build_plan([plain_pdf, tmp_path / "nope.pdf"], "smart", threshold=0.70)
    assert sp.has_errors
    assert sp.layout is None                 # no plan while a file is broken
    assert sp.entries[1].error and not sp.entries[1].ok
    assert sp.entries[0].ok


# ---- pass PDFs map to the right source pages --------------------

def test_pass_pdfs_target_correct_source_pages(cover_pdf, tmp_path):
    sp = jobs.build_plan([cover_pdf], "smart", threshold=0.70)
    even = jobs.build_pass_pdf(sp, "even", tmp_path)
    odd = jobs.build_pass_pdf(sp, "odd", tmp_path)
    with pikepdf.open(even) as p:
        assert len(p.pages) == 2          # effective page 2 (source 3) + blank pad
    with pikepdf.open(odd) as p:
        assert len(p.pages) == 2          # effective pages 1, 3 (source 2, 4)


def test_multi_file_plan_and_pass_pdfs(tmp_path):
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)    # eff 3 -> padded 4
    b = _write(tmp_path / "b.pdf", cover=False, music_pages=4)   # eff 4 (last, not padded)
    sp = jobs.build_plan([a, b], "smart", threshold=0.70)
    assert sp.n_files == 2 and not sp.has_errors
    assert sp.layout.total == 8
    assert sp.layout.starts == (1, 5)            # b starts on an odd (front) page

    even = jobs.build_pass_pdf(sp, "even", tmp_path)
    odd = jobs.build_pass_pdf(sp, "odd", tmp_path)
    with pikepdf.open(even) as p:
        assert len(p.pages) == 4          # a2, a-blank, b2, b4
    with pikepdf.open(odd) as p:
        assert len(p.pages) == 4          # a1, a3, b1, b3
