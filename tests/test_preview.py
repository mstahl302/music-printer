"""PreviewDialog: builds a block per file, Start hands the plan back."""

import time

import pytest

import main
from musicprinter import jobs
from tests.test_covers import _write

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_preview_dialog_blocks_and_start(tmp_path):
    root = main.tk.Tk()
    root.update()
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)
    b = _write(tmp_path / "b.pdf", cover=False, music_pages=4)
    setplan = jobs.build_plan([a, b], "smart", threshold=0.70)

    got = []
    dlg = main.PreviewDialog(root, setplan=setplan, on_start=got.append)
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
