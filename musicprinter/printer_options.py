"""Per-printer output options: an extensible registry plus helpers for the
dialog, the main-window summary line, persistence, and job submission.

No UI, no threads. Each option is one descriptor object in ``REGISTRY``
that knows its key, default, how it renders in the dialog (``kind``), the
short token it contributes to the main-window summary line, and how it
mutates the kwargs passed to :func:`musicprinter.printing.submit`.

See docs/spec_printer_options.md.
"""

from __future__ import annotations

from . import settings


class Option:
    """Base descriptor. Subclasses set the class attributes and override
    :meth:`summary` / :meth:`apply`."""

    key: str
    label: str
    help: str
    default: object
    kind: str = "check"                       # "check" | "radio" | "choice"
    order: int = 0
    choices: tuple[tuple[str, str], ...] = ()  # (value, label) — radio / choice only

    def coerce(self, value):
        """Return ``value`` if it's valid for this option, else the default."""
        if self.kind == "check":
            return value if isinstance(value, bool) else self.default
        return value if value in {v for v, _ in self.choices} else self.default

    def summary(self, value) -> str | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def apply(self, kw: dict, value) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class ColorMode(Option):
    key = "color_mode"
    default = "color"                         # "color" | "mono"
    kind = "radio"
    order = 10
    label = "Color"
    help = ("Black & white saves ink; color keeps chord diagrams and "
            "highlighted endings legible.")
    choices = (("color", "Color"), ("mono", "Black & white"))

    def summary(self, value) -> str:
        return "B&W" if value == "mono" else "Color"

    def apply(self, kw: dict, value) -> None:
        kw["color_mode"] = "mono" if value == "mono" else "color"


class FitToPage(Option):
    key = "fit_to_page"
    default = True
    kind = "check"
    order = 20
    label = "Resize pages to fit the sheet"
    help = "Scales each page to the printer's paper so it never pauses to ask."

    def summary(self, value) -> str | None:
        return "fit-to-page" if value else None

    def apply(self, kw: dict, value) -> None:
        kw["fit_to_page"] = bool(value)


REGISTRY: list[Option] = sorted([ColorMode(), FitToPage()], key=lambda o: o.order)


def defaults() -> dict:
    return {o.key: o.default for o in REGISTRY}


def for_printer(cfg: dict, name: str) -> dict:
    """Stored option values for the printer ``name``: each coerced to the
    option's type, missing keys filled from :func:`defaults`, unknown keys
    ignored. A missing/garbled store yields the defaults, never raises."""
    raw = cfg.get("printer_options")
    stored = raw.get(name) if isinstance(raw, dict) else None
    if not isinstance(stored, dict):
        stored = {}
    return {o.key: o.coerce(stored.get(o.key, o.default)) for o in REGISTRY}


def persist(cfg: dict, name: str, values: dict) -> None:
    """Write ``values`` under the printer ``name`` and save the settings file.
    Called from the options dialog's **Apply** — never on a bare toggle."""
    if not name:
        return
    store = cfg.get("printer_options")
    if not isinstance(store, dict):
        store = cfg["printer_options"] = {}
    store[name] = {o.key: o.coerce(values.get(o.key, o.default)) for o in REGISTRY}
    settings.save(cfg)


def summary_line(values: dict) -> str:
    """The condensed main-window line, e.g. ``"Options: Color, fit-to-page"``."""
    toks = [t for o in REGISTRY
            if (t := o.summary(values.get(o.key, o.default))) is not None]
    return "Options: " + ", ".join(toks) if toks else "Options: —"


def submit_kwargs(values: dict) -> dict:
    """Keyword args for :func:`musicprinter.printing.submit` from ``values``."""
    kw: dict = {}
    for o in REGISTRY:
        o.apply(kw, values.get(o.key, o.default))
    return kw
