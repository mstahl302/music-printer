"""Keep tests off the real user settings / log, quiet, and fast."""

import gc
import tkinter

import pytest

from musicprinter import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    d = tmp_path / "appsupport"
    monkeypatch.setattr(settings, "APP_DIR", d)
    monkeypatch.setattr(settings, "SETTINGS_PATH", d / "settings.json")
    monkeypatch.setattr(settings, "LOG_PATH", d / "music-printer.log")
    # keep the flip cue silent and CUPS polling brisk during test runs
    monkeypatch.setenv("MUSIC_PRINTER_NO_SOUND", "1")
    monkeypatch.setenv("MUSIC_PRINTER_POLL_MS", "40")
    return d


@pytest.fixture(autouse=True)
def _tk_cleanup():
    """Tk hates multiple Tk() instances per process — clear the leaked
    default root and collect between tests so widgets from a destroyed
    interpreter don't trip the next one."""
    yield
    root = getattr(tkinter, "_default_root", None)
    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    tkinter._default_root = None
    gc.collect()
