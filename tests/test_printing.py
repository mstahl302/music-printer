"""`submit()` argv construction — the reverse-order fix in particular."""

from musicprinter import printing


def _capture(monkeypatch):
    """Replace printing._run with a spy; return a dict that gets {'cmd': [...]}."""
    seen: dict = {}

    def fake_run(cmd):
        seen["cmd"] = cmd
        return "request id is P-9 (1 file(s))"

    monkeypatch.setattr(printing, "_run", fake_run)
    return seen


def test_submit_reverses_page_order_by_default(monkeypatch):
    seen = _capture(monkeypatch)
    job_id = printing.submit("/tmp/x.pdf", "P", title="t")
    assert job_id == "P-9"
    cmd = seen["cmd"]
    assert "-o" in cmd and cmd[cmd.index("-o") + 1] == "outputorder=reverse"


def test_submit_reverse_can_be_disabled(monkeypatch):
    seen = _capture(monkeypatch)
    printing.submit("/tmp/x.pdf", "P", reverse_order=False)
    assert "outputorder=reverse" not in " ".join(seen["cmd"])


def _opts(cmd):
    """Every option value that follows a '-o' flag in cmd."""
    return [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-o"]


def test_submit_defaults_to_color_no_fit(monkeypatch):
    seen = _capture(monkeypatch)
    printing.submit("/tmp/x.pdf", "P")
    opts = _opts(seen["cmd"])
    assert "print-color-mode=color" in opts
    assert "fit-to-page" not in opts


def test_submit_mono_and_fit(monkeypatch):
    seen = _capture(monkeypatch)
    printing.submit("/tmp/x.pdf", "P", color_mode="mono", fit_to_page=True)
    opts = _opts(seen["cmd"])
    assert "print-color-mode=monochrome" in opts
    assert "fit-to-page" in opts
    assert "print-color-mode=color" not in opts
