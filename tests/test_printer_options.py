"""The printer_options registry: summary line, submit kwargs, per-printer
load/coerce/persist round-trip."""

from musicprinter import printer_options as po
from musicprinter import settings


def test_defaults():
    assert po.defaults() == {"color_mode": "color", "fit_to_page": True}


def test_summary_line_all_combinations():
    assert po.summary_line({"color_mode": "color", "fit_to_page": True}) == \
        "Options: Color, fit-to-page"
    assert po.summary_line({"color_mode": "mono", "fit_to_page": True}) == \
        "Options: B&W, fit-to-page"
    assert po.summary_line({"color_mode": "color", "fit_to_page": False}) == \
        "Options: Color"
    assert po.summary_line({"color_mode": "mono", "fit_to_page": False}) == \
        "Options: B&W"


def test_summary_line_missing_keys_fall_back_to_default():
    assert po.summary_line({}) == "Options: Color, fit-to-page"


def test_submit_kwargs():
    assert po.submit_kwargs({"color_mode": "mono", "fit_to_page": False}) == \
        {"color_mode": "mono", "fit_to_page": False}
    assert po.submit_kwargs({"color_mode": "color", "fit_to_page": True}) == \
        {"color_mode": "color", "fit_to_page": True}


def test_for_printer_defaults_when_absent():
    assert po.for_printer({}, "Xerox") == {"color_mode": "color", "fit_to_page": True}
    assert po.for_printer({"printer_options": {}}, "Xerox") == po.defaults()


def test_for_printer_coerces_and_drops_unknown():
    cfg = {"printer_options": {"Xerox": {
        "color_mode": "chartreuse",     # invalid -> default
        "fit_to_page": "yes",           # not a bool -> default
        "bogus": 1,                     # unknown -> dropped
    }}}
    assert po.for_printer(cfg, "Xerox") == {"color_mode": "color", "fit_to_page": True}


def test_for_printer_reads_stored_values():
    cfg = {"printer_options": {"Xerox": {"color_mode": "mono", "fit_to_page": False}}}
    assert po.for_printer(cfg, "Xerox") == {"color_mode": "mono", "fit_to_page": False}


def test_for_printer_survives_a_garbled_store():
    assert po.for_printer({"printer_options": "nope"}, "Xerox") == po.defaults()
    assert po.for_printer({"printer_options": {"Xerox": 7}}, "Xerox") == po.defaults()


def test_persist_writes_only_registry_keys_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "APP_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    cfg = dict(settings.DEFAULTS)
    po.persist(cfg, "Xerox", {"color_mode": "mono", "fit_to_page": False, "junk": 9})
    assert cfg["printer_options"]["Xerox"] == {"color_mode": "mono", "fit_to_page": False}

    reloaded = settings.load()
    assert reloaded["printer_options"]["Xerox"] == {"color_mode": "mono", "fit_to_page": False}


def test_persist_is_a_noop_without_a_printer_name():
    cfg = {"printer_options": {}}
    po.persist(cfg, "", {"color_mode": "mono", "fit_to_page": False})
    assert cfg["printer_options"] == {}


def test_two_printers_keep_independent_options(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "APP_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    cfg = dict(settings.DEFAULTS)
    po.persist(cfg, "A", {"color_mode": "mono", "fit_to_page": True})
    po.persist(cfg, "B", {"color_mode": "color", "fit_to_page": False})
    assert po.for_printer(cfg, "A") == {"color_mode": "mono", "fit_to_page": True}
    assert po.for_printer(cfg, "B") == {"color_mode": "color", "fit_to_page": False}
