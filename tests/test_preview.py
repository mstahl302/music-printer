"""PreviewDialog: builds a block per file, carries a live strip-mode
control, and Start hands the current plan back."""

import time

import pytest

import main
from musicprinter import jobs
from tests.test_covers import _write

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(root, dlg, timeout=4.0):
    """Pump the event loop until the dialog is out of its busy state."""
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if not dlg._busy:
            return
        time.sleep(0.02)
    raise AssertionError("replan never settled")


def test_preview_dialog_blocks_and_start(tmp_path):
    root = main.tk.Tk()
    root.update()
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)
    b = _write(tmp_path / "b.pdf", cover=False, music_pages=4)
    setplan = jobs.build_plan([a, b], "smart", threshold=0.70)

    got = []
    dlg = main.PreviewDialog(root, setplan=setplan, threshold=0.70,
                             on_start=got.append)
    root.update()

    # a "requires N sheets" line and a Start button exist
    texts = [w.cget("text") for w in _all_labels(dlg)]
    assert any("requires" in t and "sheet" in t for t in texts)
    assert any("cover removed" in t for t in texts)   # the pink chip for file a

    # let any thumbnail work settle, then Start
    for _ in range(20):
        root.update(); time.sleep(0.02)
    dlg._start()
    assert got == [setplan]

    root.destroy()


def test_strip_mode_change_updates_chips_and_totals(tmp_path):
    root = main.tk.Tk()
    root.update()
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)   # smart -> cover off, eff 3
    b = _write(tmp_path / "b.pdf", cover=False, music_pages=4)
    setplan = jobs.build_plan([a, b], "smart", threshold=0.70)

    persisted = []
    dlg = main.PreviewDialog(root, setplan=setplan, threshold=0.70,
                             on_start=lambda _p: None,
                             on_mode_change=persisted.append)
    root.update()

    assert dlg._blocks[0]["chip"].grid_info() != {}       # chip shown under "smart"
    assert dlg._blocks[0]["count"].cget("text").startswith("3 pages")

    dlg._change_mode("Don't Remove")
    assert dlg._busy                                       # disabled while it recomputes
    _settle(root, dlg)

    want = jobs.build_plan([a, b], "none", threshold=0.70)
    assert dlg._setplan.strip_mode == "none"
    assert persisted == ["none"]
    assert dlg._blocks[0]["chip"].grid_info() == {}        # chip gone
    assert dlg._blocks[0]["count"].cget("text").startswith("4 pages")
    assert dlg._sheets_var.get() == (
        f"Printing requires {want.sheets_to_prepare} sheets of paper")

    # Start now hands back the re-planned SetPlan, not the original
    out = []
    dlg._on_start = out.append
    dlg._start()
    assert out[0].strip_mode == "none"

    root.destroy()


def test_rapid_mode_change_keeps_only_the_last(tmp_path):
    root = main.tk.Tk()
    root.update()
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)
    setplan = jobs.build_plan([a], "smart", threshold=0.70)

    dlg = main.PreviewDialog(root, setplan=setplan, threshold=0.70,
                             on_start=lambda _p: None)
    root.update()

    dlg._change_mode("Don't Remove")
    dlg._change_mode("Always Remove First Page")   # supersedes before the first lands
    assert dlg._replan_token == 2
    _settle(root, dlg)

    assert dlg._setplan.strip_mode == "always"     # last click wins

    root.destroy()


def test_preview_dialog_is_resizable_and_shows_more_when_grown(tmp_path):
    root = main.tk.Tk()
    root.update()
    files = [_write(tmp_path / f"s{i}.pdf", cover=False, music_pages=4)
             for i in range(8)]
    setplan = jobs.build_plan(files, "none", threshold=0.70)

    dlg = main.PreviewDialog(root, setplan=setplan, threshold=0.70,
                             on_start=lambda _p: None)
    root.update()

    assert tuple(dlg.resizable()) == (1, 1)      # was (False, False)

    frm = dlg.winfo_children()[0]
    cv = next(w for w in frm.winfo_children() if isinstance(w, main.tk.Canvas))
    winid = cv.find_all()[0]                     # the one window item (body)

    before_span = cv.yview()
    before_w = cv.winfo_width()

    dlg.geometry("700x900")
    dlg.update()

    after_span = cv.yview()
    # taller: a bigger fraction of the (fixed-height) block list is visible
    assert (after_span[1] - after_span[0]) > (before_span[1] - before_span[0])
    # wider: the inner frame follows the canvas instead of leaving a gap
    assert cv.winfo_width() > before_w
    assert int(cv.itemcget(winid, "width")) == cv.winfo_width()

    root.destroy()


def test_preview_dialog_scroll_step_is_fixed_and_small(tmp_path):
    root = main.tk.Tk()
    root.update()
    files = [_write(tmp_path / f"s{i}.pdf", cover=False, music_pages=4)
             for i in range(10)]
    setplan = jobs.build_plan(files, "none", threshold=0.70)

    dlg = main.PreviewDialog(root, setplan=setplan, threshold=0.70,
                             on_start=lambda _p: None)
    root.update()

    frm = dlg.winfo_children()[0]
    cv = next(w for w in frm.winfo_children() if isinstance(w, main.tk.Canvas))
    assert int(cv.cget("yscrollincrement")) == main.PreviewDialog.SCROLL_STEP_PX

    total_h = cv.bbox("all")[3]
    before = cv.yview()[0]
    mx = cv.winfo_rootx() + cv.winfo_width() // 2
    my = cv.winfo_rooty() + cv.winfo_height() // 2
    cv.event_generate("<MouseWheel>", delta=-40, rootx=mx, rooty=my)
    root.update()
    moved_px = (cv.yview()[0] - before) * total_h
    assert round(moved_px) == main.PreviewDialog.SCROLL_STEP_PX

    # growing the dialog doesn't grow the step — Tk's unset-increment
    # default is ~10% of the canvas's own height, which would otherwise
    # balloon now that the dialog is resizable (spec_resizable_preview.md)
    dlg.geometry("700x900")
    dlg.update()
    assert int(cv.cget("yscrollincrement")) == main.PreviewDialog.SCROLL_STEP_PX

    root.destroy()


def _all_labels(widget):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, (main.tk.Label, main.ttk.Label)):
            try:
                child.cget("text")
                out.append(child)
            except main.tk.TclError:
                pass
        out.extend(_all_labels(child))
    return out
