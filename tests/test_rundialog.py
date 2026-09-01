"""RunDialog in isolation: headings, which buttons show per phase, callbacks."""

import tkinter as tk

import pytest

from musicprinter import rundialog

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def dlg():
    root = tk.Tk()
    root.update_idletasks()
    events = []
    d = rundialog.RunDialog(
        root, run_title="Printing — x.pdf",
        on_cancel=lambda: events.append("cancel"),
        on_continue=lambda: events.append("continue"),
        on_close=lambda: events.append("close"),
    )
    d.events = events
    root.update()
    yield d
    try:
        d.destroy()
        root.destroy()
    except tk.TclError:
        pass


def _gridded(widget):
    return bool(widget.grid_info())


def test_active_phases_show_cancel_only(dlg):
    for phase in (rundialog.PREPARING, rundialog.PRINTING):
        dlg.show_phase(phase, detail="…")
        assert _gridded(dlg._cancel_btn)
        assert not _gridded(dlg._primary_btn)


def test_flip_phase_shows_continue_and_cancel(dlg):
    dlg.show_phase(rundialog.FLIP)
    assert _gridded(dlg._cancel_btn)
    assert _gridded(dlg._primary_btn)
    assert dlg._primary_btn.cget("text") == "Continue — print the back side"
    assert "SHORT edge" in dlg._instr.cget("text")


@pytest.mark.parametrize("phase,heading", [
    (rundialog.DONE, "Done"),
    (rundialog.CANCELLED, "Job cancelled"),
    (rundialog.FAILED, "Couldn't finish"),
])
def test_terminal_phases_show_close_only(dlg, phase, heading):
    dlg.show_phase(phase, detail="msg")
    assert not _gridded(dlg._cancel_btn)
    assert _gridded(dlg._primary_btn)
    assert dlg._primary_btn.cget("text") == "Close"
    assert dlg._heading.cget("text") == heading


def test_primary_button_routes_by_phase(dlg):
    dlg.show_phase(rundialog.FLIP)
    dlg._primary()
    dlg.show_phase(rundialog.DONE, detail="ok")
    dlg._primary()
    assert dlg.events == ["continue", "close"]


def test_cancel_button_only_fires_when_active(dlg):
    dlg.show_phase(rundialog.DONE, detail="ok")
    dlg._cancel()                       # ignored at a terminal phase
    dlg.show_phase(rundialog.PRINTING, detail="…")
    dlg._cancel()
    assert dlg.events == ["cancel"]


def test_window_close_box_maps_to_cancel_or_close(dlg):
    dlg.show_phase(rundialog.PRINTING, detail="…")
    dlg._closed()
    dlg.show_phase(rundialog.CANCELLED, detail="stopped")
    dlg._closed()
    assert dlg.events == ["cancel", "close"]
