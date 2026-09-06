"""OptionsDialog: renders one block per registry entry per its kind,
Apply fires on_apply with the draft, the close box does not."""

import pytest

import main
from musicprinter import printer_options as po

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _widgets(w, cls):
    out = []
    for c in w.winfo_children():
        if isinstance(c, cls):
            out.append(c)
        out.extend(_widgets(c, cls))
    return out


def test_dialog_renders_a_control_per_option(tmp_path):
    root = main.tk.Tk()
    root.update()
    applied = []
    dlg = main.OptionsDialog(root, printer_label="Xerox Phaser",
                             values=po.defaults(), on_apply=applied.append)
    root.update()

    # radio group for color (two buttons), checkbox for fit
    radios = _widgets(dlg, main.ttk.Radiobutton)
    checks = _widgets(dlg, main.ttk.Checkbutton)
    assert {r.cget("value") for r in radios} == {"color", "mono"}
    assert len(checks) == 1

    # initial selection reflects the passed-in values
    assert dlg._vars["color_mode"].get() == "color"
    assert dlg._vars["fit_to_page"].get() is True

    # the printer label is shown
    labels = [w.cget("text") for w in _widgets(dlg, main.ttk.Label)]
    assert any("Xerox Phaser" in t for t in labels)

    root.destroy()


def test_apply_reports_the_draft_and_closes(tmp_path):
    root = main.tk.Tk()
    root.update()
    applied = []
    dlg = main.OptionsDialog(root, printer_label="P",
                             values=po.defaults(), on_apply=applied.append)
    root.update()

    dlg._vars["color_mode"].set("mono")
    dlg._vars["fit_to_page"].set(False)
    dlg._apply()

    assert applied == [{"color_mode": "mono", "fit_to_page": False}]
    assert not dlg.winfo_exists()
    root.destroy()


def test_close_box_discards_without_calling_on_apply(tmp_path):
    root = main.tk.Tk()
    root.update()
    applied = []
    dlg = main.OptionsDialog(root, printer_label="P",
                             values=po.defaults(), on_apply=applied.append)
    root.update()

    dlg._vars["color_mode"].set("mono")
    dlg._discard()

    assert applied == []
    assert not dlg.winfo_exists()
    root.destroy()
