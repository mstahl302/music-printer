"""Drive the two-pass state machine headlessly with printing.* mocked.

No real CUPS calls. Covers a single-file list, a multi-file list, the
single-page shortcut, the run dialog phases, the flip cue, and cancel.
"""

import time

import pytest

import main
from musicprinter.printing import Printer
from tests.test_covers import _write

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class FakePrinting:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.submitted = []          # lp -t title per submit
        self.canceled = []
        self._n = 0

    def list_printers(self):
        return [Printer("FakePrinter", True)]

    def printer_state(self, name):
        return "idle"

    def submit(self, path, printer, *, title=None, **kw):
        self.submitted.append(title)
        return f"FAKE-{len(self.submitted)}"

    def job_status(self, job_id):
        if self._n < len(self.statuses):
            self._n += 1
        return self.statuses[min(self._n, len(self.statuses)) - 1]

    def cancel(self, job_id):
        self.canceled.append(job_id)


@pytest.fixture
def no_dialogs(monkeypatch):
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(main.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *a, **k: True)


def _pump(app, until, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out in state {app.state!r}")


def _app_with(monkeypatch, fake, pdfs):
    monkeypatch.setattr(main, "printing", fake)
    app = main.App()
    app.update()
    app.filelist.set_files(list(pdfs))
    app._recompute()
    _pump(app, lambda: app.setplan is not None)
    return app


def _passes(fake):
    return [t.rsplit(" · ", 1)[1] for t in fake.submitted]


def test_single_file_two_pass(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "c.pdf", cover=True, music_pages=4)     # eff 4 -> two pass
    app = _app_with(monkeypatch, fake, [pdf])

    app._start_run(app.setplan)
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)
    assert app.dialog.phase == "flip"

    app._start_pass2()
    _pump(app, lambda: app.state == main.DONE)
    assert _passes(fake) == ["even", "odd"]
    assert app.dialog._primary_btn.cget("text") == "Close"

    printer_before, cover_before = app.printer.get(), app.cover_label.get()
    app._close_dialog()                         # click "Close" on the done dialog
    assert app.filelist.files == []             # set cleared, ready for the next run
    assert app.setplan is None
    assert app.state == main.READY
    assert (app.printer.get(), app.cover_label.get()) == (printer_before, cover_before)
    app._on_close()


def test_multi_file_run(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    a = _write(tmp_path / "a.pdf", cover=True, music_pages=3)
    b = _write(tmp_path / "b.pdf", cover=False, music_pages=4)
    c = _write(tmp_path / "c.pdf", cover=False, music_pages=6)
    app = _app_with(monkeypatch, fake, [a, b, c])
    assert app.setplan.n_files == 3
    assert app.dialog is None

    app._start_run(app.setplan)
    assert app.dialog.title() == "Printing — 3 songs"
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)
    app._start_pass2()
    _pump(app, lambda: app.state == main.DONE)
    assert _passes(fake) == ["even", "odd"]
    app._on_close()


def test_single_page_skips_flip(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "s.pdf", cover=True, music_pages=1)     # eff 1 -> single pass
    app = _app_with(monkeypatch, fake, [pdf])
    assert app.setplan.single_pass is True

    app._start_run(app.setplan)
    _pump(app, lambda: app.state == main.DONE)
    assert _passes(fake) == ["single"]
    app._on_close()


def test_preview_blocked_by_unopenable_file(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    good = _write(tmp_path / "g.pdf", cover=False, music_pages=4)
    app = _app_with(monkeypatch, fake, [good, tmp_path / "missing.pdf"])
    assert app.setplan.has_errors
    assert app._preview_ok() is False
    assert not app.preview_btn._enabled
    app._on_close()


def test_flip_cue_plays_ping(tmp_path, monkeypatch, no_dialogs):
    monkeypatch.delenv("MUSIC_PRINTER_NO_SOUND", raising=False)
    calls = []
    monkeypatch.setattr(main.subprocess, "Popen",
                        lambda cmd, **kw: calls.append(cmd) or _Dummy())
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "c.pdf", cover=False, music_pages=4)
    app = _app_with(monkeypatch, fake, [pdf])
    app._start_run(app.setplan)
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)
    assert calls == [["afplay", main.FLIP_SOUND]]
    app._on_close()


def test_cancel_during_pass1_returns_to_ready(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["processing"])
    pdf = _write(tmp_path / "c.pdf", cover=False, music_pages=4)
    app = _app_with(monkeypatch, fake, [pdf])
    app._start_run(app.setplan)
    _pump(app, lambda: app.state == main.PRINTING_PASS1 and app._job_id is not None)

    fake.statuses = ["canceled"]
    fake._n = 0
    app._cancel()
    _pump(app, lambda: app.state == main.READY)
    assert fake.canceled == ["FAKE-1"]
    app._on_close()


def test_cancel_during_pass2_warns_about_feed_tray(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "c.pdf", cover=False, music_pages=4)
    app = _app_with(monkeypatch, fake, [pdf])
    app._start_run(app.setplan)
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)

    fake.statuses = ["processing"]
    fake._n = 0
    app._start_pass2()
    _pump(app, lambda: app.state == main.PRINTING_PASS2 and app._job_id is not None)

    fake.statuses = ["canceled"]
    fake._n = 0
    app._cancel()
    _pump(app, lambda: app.state == main.DONE_ERROR)
    assert app.dialog.phase == "cancelled"
    assert "feed tray" in app.dialog._detail.cget("text")
    assert fake.canceled == ["FAKE-2"]

    app._close_dialog()
    assert app.filelist.files == [pdf]          # a cancelled run keeps the set
    app._on_close()


class _Dummy:
    def poll(self):
        return 0
