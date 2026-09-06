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
