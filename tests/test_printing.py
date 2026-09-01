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
