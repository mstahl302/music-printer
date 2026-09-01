"""Keep tests off the real user settings / log under ~/Library/Application Support."""

import pytest

from musicprinter import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    d = tmp_path / "appsupport"
    monkeypatch.setattr(settings, "APP_DIR", d)
    monkeypatch.setattr(settings, "SETTINGS_PATH", d / "settings.json")
    monkeypatch.setattr(settings, "LOG_PATH", d / "music-printer.log")
    return d
