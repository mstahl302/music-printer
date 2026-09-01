"""Drive the two-pass state machine headlessly with printing.* mocked out.

No real CUPS calls: submit returns fake job ids, job_status is scripted.
Verifies the READY -> PASS1 -> WAIT_FOR_FLIP -> PASS2 -> DONE path, the
single-page shortcut, and cancel.
"""

import time

import pymupdf
import pytest

import main
from musicprinter.printing import Printer
from tests.test_covers import _write

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class FakePrinting:
    """Stand-in for musicprinter.printing, scripted per test."""

    def __init__(self, statuses):
        self.statuses = list(statuses)      # values job_status returns, in order
        self.submitted = []                 # (title,) per submit
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
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *a, **k: True)


def _pump(app, until, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if until():
            return
        time.sleep(0.03)
    raise AssertionError(f"timed out in state {app.state!r}")


def _app_with(monkeypatch, fake, pdf):
    monkeypatch.setattr(main, "printing", fake)
    app = main.App()
    app.update()
    app.source_path = pdf
    app.file_label.config(text=pdf.name)
    app._recompute_plan()
    _pump(app, lambda: app.plan is not None)
    return app


def test_two_pass_happy_path(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "c.pdf", cover=True, music_pages=4)  # n_eff = 4 -> two pass
    app = _app_with(monkeypatch, fake, pdf)

    app._start()
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)

    app._start_pass2()
    _pump(app, lambda: app.state == main.DONE)

    assert [t.rsplit(" — ", 1)[1] for t in fake.submitted] == ["even", "odd"]
    app._on_close()


def test_single_page_skips_flip(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "s.pdf", cover=True, music_pages=1)  # n_eff = 1 -> single
    app = _app_with(monkeypatch, fake, pdf)
    assert app.plan.passes.single_pass is True

    app._start()
    _pump(app, lambda: app.state == main.DONE)

    assert len(fake.submitted) == 1 and fake.submitted[0].endswith("single")
    app._on_close()


def test_cancel_during_pass1_returns_to_ready(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["processing"])
    pdf = _write(tmp_path / "c.pdf", cover=False, music_pages=4)
    app = _app_with(monkeypatch, fake, pdf)

    app._start()
    _pump(app, lambda: app.state == main.PRINTING_PASS1 and app._job_id is not None)

    fake.statuses = ["canceled"]          # next poll reports the cancel landed
    fake._n = 0
    app._cancel()
    _pump(app, lambda: app.state == main.READY)

    assert fake.canceled == ["FAKE-1"]
    app._on_close()


def test_odd_effective_count_pads_pass1(tmp_path, monkeypatch, no_dialogs):
    fake = FakePrinting(["completed"])
    pdf = _write(tmp_path / "c.pdf", cover=True, music_pages=5)  # n_eff = 5 -> pad blank
    app = _app_with(monkeypatch, fake, pdf)
    assert app.plan.passes.pad_blank is True

    app._start()
    _pump(app, lambda: app.state == main.WAIT_FOR_FLIP)
    import pikepdf
    pass1 = next(app._tmpdir.glob("*pass1.pdf"))
    with pikepdf.open(pass1) as p:
        assert len(p.pages) == 3          # effective pages 2, 4 + blank
    app._start_pass2()
    _pump(app, lambda: app.state == main.DONE)
    app._on_close()
