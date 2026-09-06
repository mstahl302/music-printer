# Feature Spec — Printer Options

**Feature:** delivers **#18 — print in color** and **#19 — fit every
page to the tray size** in [feature_requests.md](feature_requests.md).
Also lays the **per-printer options mechanism** that #3, #4, #5, #6, #7
and #10 all plug into.
**Status:** DRAFT — not yet built.
**Date:** 2026-09-06
**Owner:** markstahl

> Reconciliation with the shipped specs is by appendix, not by rewriting
> them (see the repo convention). When this ships,
> [specification.md](specification.md) gets **Appendix C.5** plus inline
> ⚠ asides at §2, §4.1, §4.2, §7.4 and §11/Q3; **#18** and **#19** are
> pruned from `feature_requests.md`. The exact edits are listed in
> [§10](#10-doc-maintenance-when-this-ships). This file is the authority
> for printer options.

---

## 1. Summary

Add a **gear button** to the right of the printer picker. It opens a
small **modal options dialog** whose controls configure how jobs are
sent to *that* printer; **Apply** commits them. Directly under the
printer picker, a one-line **condensed summary** ("Options: Color,
fit-to-page") shows what is currently selected without opening the
dialog.

The selected options are **saved per printer** and reload with the app,
so a printer that was set to black & white last week is still black &
white today, and switching printers switches the options with it.

This first cut ships **two** options — **color vs. black & white**
(default color) and **resize to fit** (default on) — and the
**registry, summary-line, persistence and submit-wiring pattern** that
every later option ([§8](#8-roadmap--every-option-in-the-backlog)) drops
into by adding one descriptor object.

## 2. Problem / value

`printing.submit` today sends both passes with no color or scaling
options at all — whatever the driver defaults to. Two concrete failures:

- **Color (#18).** Engraved sheet music increasingly ships color —
  chord diagrams, highlighted repeats/endings, capo labels, publisher
  accents. A grayscale job flattens those to near-invisible mid-grays.
  The two-pass workflow makes a wrong default expensive: you don't
  notice until the whole flipped stack is on the tray.
- **Page size (#19).** A PDF that's A4, or Letter-with-a-hair-off, makes
  the printer stop mid-run and wait for input — which defeats the guided
  run dialog's whole point (don't make the human babysit the run).
  `-o fit-to-page` scales each page to the tray's media so the printer
  never has to negotiate a size.

Both are **per-printer, set-once, rarely-touched** facts — exactly the
kind of thing [feature_requests.md #3](feature_requests.md) wants off the
main window and [#10](feature_requests.md) wants bound to the printer.
Rather than grow the main window a checkbox at a time, this establishes
**one place** they live and **one line** that reports them.

## 3. Concepts — the pattern

| Concept | Meaning |
|---|---|
| **Option** | One configurable fact about how jobs go to a printer. Has a key, a default, a control in the dialog, a summary rule, and a submit effect. |
| **Option registry** | An ordered list of option descriptors ([§4.3](#43-the-option-registry)). Adding an option = adding one entry; the dialog, the summary line, persistence and submit wiring all read the registry. |
| **Per-printer values** | `{option key → value}` for one printer, stored under that printer's CUPS queue name. A printer with no stored entry uses every option's default. |
| **Summary token** | The short string an option contributes to the main-window summary line — or `None` to contribute nothing. |
| **Always-shown vs. only-when-set** | An option whose `summary(value)` is non-`None` for *every* value is **always shown** (color/B&W). One that returns `None` for its default is **only shown when set** (fit-to-page). This is a property of the descriptor, not a separate flag. |

The design goal: the main window stays as calm as it is now (printer,
list, Preview) while the user can still *see* at a glance what they're
about to get, and *change* it in two clicks.

## 4. Design

### 4.1 Where it lives on the main window

`App._build` today puts the printer `OptionMenu` across grid columns 1–2
of `frm` (row 0), with the paused-printer warning on row 1 and the file
list on row 2.

Changes:

1. **Gear button.** Shrink the `OptionMenu` to column 1 (`sticky="ew"`,
   `frm` keeps `columnconfigure(1, weight=1)`); add a compact button in
   column 2 (`sticky="e"`). A `ttk.Button(text="⚙", width=3,
   command=self._open_options)` — neutral, not a `widgets.Button`
   (those are for colored primary actions). If the glyph renders badly
   on aqua Tk 9, fall back to `text="Options…"` ([§13](#13-resolved-decisions-2026-09-06) #8).
   Disabled whenever `state != READY` (added to `_set_state`, alongside
   `printer_menu`).
2. **Summary line.** A new row **directly under** the printer picker
   (push the warning and everything below down one row):
   `ttk.Label(frm, textvariable=self.options_summary, foreground="#888",
   font=("TkDefaultFont", 10))` — small, muted, modest contrast,
   left-aligned, `columnspan=2` under the menu. It is **advisory only —
   not a control**: no click target, no hover. The gear is the only way
   in. Always present; never empty (color always contributes a token —
   [§4.4](#44-the-summary-line)).
3. The **paused-printer warning** keeps its own row, now *below* the
   summary line. Two short muted lines under the picker is fine; they're
   rarely both non-trivial at once.

New row order in `frm`: `0` printer + gear · `1` options summary · `2`
printer warning · `3` file list · `4` Add / Preview · `5` status.

### 4.2 The options dialog

A modal `Toplevel` — `transient(parent)` + `grab_set`, not resizable, no
minimize — following the `RunDialog` / `PreviewDialog` shape but much
simpler: **no worker thread, no recompute, no queue.** The two first
options only affect the `lp` command line at submit time; they don't
touch page planning, sheet counts, or thumbnails.

The dialog edits a **local draft** — a copy of the current values it was
handed. Ticking a box changes only that draft. Nothing reaches
`self._printer_opts`, the settings file, or the summary line until the
user clicks **Apply**. Closing the window any other way (the close box,
Cmd-W) **discards the draft** — the printer's options stay exactly as
they were.

Contents, top to bottom:

- **Header.** "Options for *Xerox Phaser (Windermere)*" (the printer's
  `label`).
- **One block per option**, built by walking the registry and switching
  on `spec.kind` ([§4.3](#43-the-option-registry)): a `check` renders one
  `ttk.Checkbutton`; a `radio` renders `spec.label` as a small heading
  then a `ttk.Radiobutton` per `spec.choices` sharing one draft
  `StringVar`. Each block gets a muted `spec.help` sub-label. No
  `command` callbacks — a control just updates its draft var.
  `self._vars[spec.key]` holds the draft var for each option.
- **Apply** button (`widgets.button(..., BLUE)`), plus
  `protocol("WM_DELETE_WINDOW", self._discard)`. Apply is the **only**
  commit; there is no separate Cancel (the close box is the cancel).

`_apply()` → read every draft var in `self._vars` into a dict (bool for
`check`, the chosen value for `radio` / `choice`), write it to
`self._printer_opts`, call
`printer_options.persist(self.cfg, printer_name, self._printer_opts)`
(which does `cfg["printer_options"][name] = …; settings.save(cfg)`),
call `self._refresh_options_summary()`, then close the dialog.

`_discard()` → just close. Nothing is read back.

`OptionsDialog` takes `printer_label`, `values` (copied into the draft),
and `on_apply(values)`; `App` wires `on_apply` to the persist + refresh
above. Opening it again always starts from the committed values.

### 4.3 The option registry

New module `musicprinter/printer_options.py`. No UI, no I/O — pure
descriptors + helpers, unit-testable like `duplex.py`.

```python
@dataclass(frozen=True)
class Option:
    key:     str                       # settings + submit-kwarg key
    label:   str                       # dialog row label
    help:    str                       # muted sub-label
    default: bool | str
    kind:    str                       # "check" | "radio" | "choice"
    order:   int                       # dialog + summary ordering
    choices: tuple[tuple[str, str], ...] = ()   # (value, label) — radio / choice only

    def summary(self, value) -> str | None:
        """Token for the main-window line, or None to contribute nothing."""

    def apply(self, kw: dict, value) -> None:
        """Mutate the kwargs dict passed to printing.submit()."""


class ColorMode(Option):
    key, default, kind, order = "color_mode", "color", "radio", 10
    label   = "Color"
    help    = "Black & white saves ink; color keeps chord diagrams and highlighted endings legible."
    choices = (("color", "Color"), ("mono", "Black & white"))
    def summary(self, v):  return "B&W" if v == "mono" else "Color"
    def apply(self, kw, v): kw["color_mode"] = v


class FitToPage(Option):
    key, default, kind, order = "fit_to_page", True, "check", 20
    label = "Resize pages to fit the sheet"
    help  = "Scales each page to the printer's paper so it never pauses to ask."
    def summary(self, v):  return "fit-to-page" if v else None
    def apply(self, kw, v): kw["fit_to_page"] = bool(v)


REGISTRY: list[Option] = sorted([ColorMode(), FitToPage()], key=lambda o: o.order)
```

Helpers:

```python
def defaults() -> dict:
    return {o.key: o.default for o in REGISTRY}

def for_printer(cfg: dict, name: str) -> dict:
    """Stored values for `name`, each coerced to the option's type, missing
    keys filled from defaults(). Unknown stored keys are ignored."""

def persist(cfg: dict, name: str, values: dict) -> None:
    # called only from the dialog's Apply — never on a bare toggle
    cfg.setdefault("printer_options", {})[name] = {o.key: values[o.key] for o in REGISTRY}
    settings.save(cfg)

def summary_line(values: dict) -> str:
    toks = [t for o in REGISTRY if (t := o.summary(values[o.key])) is not None]
    return "Options: " + ", ".join(toks) if toks else "Options: —"

def submit_kwargs(values: dict) -> dict:
    kw: dict = {}
    for o in REGISTRY:
        o.apply(kw, values[o.key])
    return kw
```

`kind` is stored on the descriptor so each option carries its own
presentation:

| `kind` | Control | Value |
|---|---|---|
| `check` | one `ttk.Checkbutton` (`label` is its text) | `bool` |
| `radio` | `label` as a small row heading, then one `ttk.Radiobutton` per `choices` entry over a shared draft var | one of `choices` values (`str`) |
| `choice` | `label` + a `ttk.OptionMenu` over `choices` | one of `choices` values (`str`) |

Color is a **radio** (`Color` / `Black & white`) — a two-way pick with
named states reads better than an inverted checkbox. `summary`, `persist`,
`for_printer` and `submit_kwargs` are value-agnostic, so a new option is a
descriptor plus — only if it needs a `kind` not listed above — one more
branch in the dialog's render loop.

### 4.4 The summary line

`summary_line(values)` → `"Options: " + ", ".join(tokens)` in registry
order, where each option contributes `spec.summary(value)` or nothing:

| Values | Line |
|---|---|
| color, fit on (**defaults**) | `Options: Color, fit-to-page` |
| B&W, fit on | `Options: B&W, fit-to-page` |
| color, fit off | `Options: Color` |
| B&W, fit off | `Options: B&W` |

Color is the worked example of an **always-shown** option — even at its
default it reassures the user (especially right after they set a
*different* printer to B&W). Fit-to-page is the **only-when-set** example.
Later options ([§8](#8-roadmap--every-option-in-the-backlog)) each pick
one behavior; the table in §8 says which and why.

`App` holds `self.options_summary = tk.StringVar()` and
`self._printer_opts: dict`. `_refresh_options_summary()` sets the var
from `printer_options.summary_line(self._printer_opts)`. Called from:
`__init__` (after the first `for_printer`), `_choose_printer` /
`_load_printers` (after reloading `_printer_opts` for the new printer),
and the dialog's `on_apply` (never on a bare toggle).

### 4.5 Per-printer persistence

`settings.DEFAULTS` gains one key:

```python
"printer_options": {},   # { queue_name: { "color_mode": "color"|"mono", "fit_to_page": bool } }
```

`settings.load` already type-checks each top-level key against
`DEFAULTS` (`isinstance(raw[key], dict)` here — passes) and `settings.save`
already round-trips any `DEFAULTS` key, so the nested map needs **no**
change to `settings.py` beyond the one default. Inner structure is not
validated on load — `printer_options.for_printer` is where each value is
coerced (`"mono"`/`"color"` else default; `bool(...)` for flags) and
unknown keys dropped, so a hand-edited or stale file can't crash the app.

Keying is by **`Printer.name`** (the stable CUPS queue name), the same
identifier `last_printer` already persists — never `label` (the
description string, which the user can rename in System Settings).

`App` flow:

- `__init__`: `self._printer_opts = printer_options.for_printer(self.cfg,
  self.printer.get())` after `cfg` loads, then `_refresh_options_summary()`.
- `_choose_printer(name)`: after `self.printer.set(name)` and the
  existing `settings.save`, add
  `self._printer_opts = printer_options.for_printer(self.cfg, name)` and
  `self._refresh_options_summary()`.
- `_load_printers`: when it falls back to the default/first printer
  because the stored `last_printer` is gone, reload `_printer_opts` for
  whatever it landed on.
- A printer that isn't in `self._printers` (offline, or a stored name
  that no longer resolves) still gets options — they're keyed by the
  string, and `submit` will just pass the flags to `lp -d <name>` as
  usual.

### 4.6 Submit wiring

`_submit_worker` builds the `lp` call. Add:

```python
opt_kw = printer_options.submit_kwargs(self._printer_opts)
job_id = printing.submit(pdf, printer_name,
                         title=f"{setplan.run_title} · {which}",
                         reverse_order=reverse,
                         **opt_kw)                      # color_mode=…, fit_to_page=…
```

Both passes read the **same** `self._printer_opts`, so color / fit are
identical across pass 1 and pass 2 (and the single-pass path). The
`settings.log` line gains `color={} fit={}` next to the existing
`mode=` / `reverse=`.

`printing.submit` gains one parameter; `fit_to_page` already exists and
is currently never passed:

```python
def submit(path, printer=None, *, copies=1, two_sided=False,
           fit_to_page=False, reverse_order=True,
           color_mode="color",          # NEW: "color" | "mono"
           title=None) -> str:
    ...
    if fit_to_page:
        cmd += ["-o", "fit-to-page"]
    if color_mode == "mono":
        cmd += ["-o", "print-color-mode=monochrome"]
    elif color_mode == "color":
        cmd += ["-o", "print-color-mode=color"]
```

`print-color-mode` is the standardized CUPS/IPP attribute and is the
right first choice; some older drivers only honor `ColorModel=Gray` /
`-o ColorModel=KGray`. Driver-specific fallbacks are out of scope for v1
([§13](#13-resolved-decisions-2026-09-06) #3). Sending
`print-color-mode=color` explicitly (rather than omitting it) is
deliberate — it stops a driver whose *own* default is grayscale from
quietly flattening a color score.

## 5. The two first options in detail

### 5.1 Color vs. black & white (#18)

- **Control:** a **radio group** headed "Color" with two buttons —
  **Color** and **Black & white** — one selected at all times
  (`kind="radio"`, `choices = (("color","Color"), ("mono","Black & white"))`).
- **Default:** `"color"`. Color by default, switch to B&W to save ink —
  exactly [#18](feature_requests.md).
- **Summary:** always shown — `"Color"` or `"B&W"`.
- **Submit:** `-o print-color-mode=color` / `=monochrome` on **both**
  passes.
- **No effect** on planning, sheets, thumbnails, or the state machine.

### 5.2 Resize to fit (#19)

- **Control:** one checkbox, **"Resize pages to fit the sheet"**,
  **checked** by default (⇒ `fit_to_page = True`).
- **Default:** on. This **reverses** [specification.md
  §11/Q3](specification.md#11-resolved-decisions) ("No auto-fit; fixed
  off, print at 100 %") and the §2 / §4.2 "no scaling" non-goal — a
  deliberate, documented reopening (§10, and the feature-request doc's
  own note that #19 revisits §4.2 / §7.4).
- **Summary:** only when on — `"fit-to-page"`, nothing when off.
- **Submit:** `-o fit-to-page` on every pass when on.
- **This is the `lp -o fit-to-page` flag and nothing more.** CUPS scales
  each page to the destination media at print time; the app does not
  rewrite MediaBoxes or re-impose content. That covers #19's practical
  goal (the printer never pauses on an odd page size). Generated blank
  pad pages keep matching the last EVEN page's box and are scaled with
  everything else, so a mixed-size set still comes out uniform.

## 6. Mockups

### 6.1 Main window (options at their defaults)

```
┌─ Music Printer ───────────────────────────────────────────────┐
│                                                              │
│   Printer:  [ Xerox Phaser (Windermere)  (default)  ▾ ]  [⚙] │
│   Options: Color, fit-to-page                                 │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ ⠿  Along the Way.pdf                    6 pages    × │  │
│   │ ⠿  Best Part.pdf                        6 pages    × │  │
│   │    Add PDFs to build your set…                        │  │
│   │                                                      │  │
│   │                                                      │  │
│   │                                                      │  │
│   └──────────────────────────────────────────────────────┘  │
│   [ Add PDFs… ]                                 [  Preview  ] │
│   2 files · 6 sheets of paper                                 │
└──────────────────────────────────────────────────────────────┘
```

Same window, this printer set to B&W and a paused queue:

```
│   Printer:  [ HP LaserJet 4  ▾ ]                         [⚙] │
│   Options: B&W, fit-to-page                                   │
│   This printer is paused — jobs will queue but not print.     │
```

### 6.2 Options dialog

```
┌─ Printer Options ─────────────────────────────────────┐
│                                                      │
│   Options for Xerox Phaser (Windermere)               │
│   ────────────────────────────────────────────────    │
│                                                      │
│   Color                                               │
│      ( • ) Color        ( ) Black & white             │
│      Black & white saves ink; color keeps chord       │
│      diagrams and highlighted endings legible.        │
│                                                      │
│   ☑  Resize pages to fit the sheet                    │
│      Scales each page to the printer's paper so it    │
│      never pauses to ask.                             │
│                                                      │
│   ────────────────────────────────────────────────    │
│                                         [   Apply   ] │
└──────────────────────────────────────────────────────┘
```

Blocks appear in `REGISTRY` order (`order` field) — Color (radio) then
Resize (checkbox). Each `kind` renders its own control
([§4.3](#43-the-option-registry)). The dialog is sized to its content;
later options just make it taller. **Apply** commits the current
selections and closes; closing the window without Apply leaves the
printer's options untouched.

## 7. Behavior details / edge cases

| Case | Behavior |
|---|---|
| **Switch printer** | `_printer_opts` reloads for the new queue name; summary line updates; an open options dialog is not expected (gear is disabled unless `READY`, and opening the dialog is modal). |
| **First time on a printer** | No stored entry → every option at its default (`Color`, `fit-to-page`). Nothing is written until the user clicks Apply. |
| **Toggle a box in the dialog** | Changes the dialog's local draft only. `self._printer_opts`, the settings file, and the summary line are all untouched. |
| **Apply** | Draft → `self._printer_opts`; `settings.save`; summary line refreshes; dialog closes. The only commit path. |
| **Close the dialog without Apply** (close box, Cmd-W, app quit) | Draft discarded. The printer's options remain exactly as they were. |
| **Options dialog during a run** | Can't happen — the gear is disabled whenever `state != READY` (same rule as the printer menu and Add button). |
| **Stored file hand-edited / stale key** | `for_printer` coerces each value and drops unknown keys; a bad value falls back to that option's default. No crash. |
| **Printer removed from the system** | Its `printer_options` entry is left in the file (harmless; re-adopted if the queue name comes back). Not garbage-collected in v1. |
| **Unknown / offline selected printer** | Options still apply — keyed by the name string; `lp -d <name>` gets the flags regardless. |
| **`fit-to-page` + generated blank** | Blank still matches the last EVEN page's media box; `fit-to-page` scales it with the rest. Mixed-size sets come out uniform. |
| **Color on a mono-only printer** | `print-color-mode=color` is harmless — the driver ignores what it can't do. |
| **Summary with nothing to show** | Can't occur while color is always-shown; `summary_line` still guards with `"Options: —"`. |

## 8. Roadmap — every option in the backlog

Every configurable item in [feature_requests.md](feature_requests.md),
and how it lands on this mechanism. **One at a time** — this spec builds
only rows 1–2. Rows 3–5 add an `Option` descriptor (row 4 also needs
state-machine work); rows 6–8 are work *around* the mechanism and are
called out as such.

| # | Backlog item | Shape on this mechanism | Key / default | Summary token | Extra work beyond a descriptor |
|---|---|---|---|---|---|
| **1** | **#18 color** | radio "Color" / "Black & white" | `color_mode` / `"color"` | **always**: `Color` / `B&W` | `printing.submit` gains `color_mode` → `print-color-mode`. **This spec.** |
| **2** | **#19 fit-to-page** | checkbox "Resize pages to fit the sheet" | `fit_to_page` / `True` | when on: `fit-to-page` | wire existing `submit(fit_to_page=…)`. **This spec.** |
| **3** | **#5** page order per-printer | checkbox "This printer reverses page order" | `reverse_page_order` / `True` | when **off**: `front-to-back order` | **Migration:** move the existing *global* `reverse_page_order` (settings.py, `_submit_worker`) into `for_printer`; one-time copy of the old global value into the current printer's entry on first load. `submit` already takes `reverse_order`. |
| **4** | **#4** true duplex | checkbox "This printer can print double-sided itself" | `true_duplex` / `False` | when on: `true duplex` (always visible when set — it changes everything) | **State machine:** when on, `_start_run` sends **one** job with `submit(two_sided=True)` and skips `WAIT_FOR_FLIP` entirely; `duplex.plan_*` is bypassed; the run dialog shows a single "Printing…" phase. Biggest of the roadmap. Pairs with `lpoptions -l` capability probing to pre-tick it. |
| **5** | **#6** 180° back-side rotation | checkbox "Rotate the back side 180°" | `rotate_back_180` / `False` | when on: `back-rotated` | `build_pass_pdf(plan, "odd", …)` rotates every page 180° before writing when the flag is set (new arg threaded from `_submit_worker`). Pure `pdfio` change; no state-machine impact. |
| **6** | **#3** extended printer-setup dialog | **is** this dialog | — | — | Once rows 3–5 exist the dialog naturally splits into an **Output** group (color, fit) and a **Printer behavior** group (page order, duplex, rotation) with a subheading between them. No new window — #3 is satisfied by grouping. |
| **7** | **#10** printer profiles | **is** `printer_options[name]` | — | — | Per-printer persistence ([§4.5](#45-per-printer-persistence)) is the whole of #10 for options that live here (3–5). Nothing extra once keying is by queue name. |
| **8** | **#7** welcome / calibration flow | **writes** `printer_options[name]` for keys 3–5 | — | — | Separate wizard `Toplevel`; from the user's answers to a test print it sets `reverse_page_order`, `true_duplex`, `rotate_back_180` for the chosen printer via `printer_options.persist`, then the main window's summary line reflects it. The flow is its own spec; this mechanism is its storage target. |

**Not printer options** — captured so the boundary is explicit:

| # | Why it isn't here | Where it belongs |
|---|---|---|
| **#9** copies > 1 | a per-*run* choice, not a sticky per-printer fact | a field on the Preview dialog; `submit(copies=…)` already exists |
| **#12** per-file cover-strip override | per-*file*, per-run | the Preview dialog's per-row control (its own spec) |
| **#8** export to two PDFs | an alternative *action*, not a modifier of a print | a second button next to Preview / Start |
| **#11** saved set-lists | about the file list, not the printer | its own feature |
| **#13** more cover vendors · **#14** full-doc preview · **#15** retry a pass · **#16** Win/Linux port | not user-configurable at all | n/a |
| **#17** dock-icon bounce | an **app-wide** preference, not per printer | a future app "Preferences" dialog, separate from this per-printer one |

## 9. Non-goals

- **Any option beyond color and fit-to-page.** Rows 3–8 of §8 are the
  plan, not the delivery.
- **Page-size normalization** — rewriting page MediaBoxes to US Letter,
  re-imposing content, `-o media=Letter`. Considered and **dropped** as
  speculative; `fit-to-page` covers the practical need. Not on the
  roadmap.
- **A separate Cancel button.** The window close box is the cancel — it
  discards the draft. **Apply** is the only commit; there is no
  persist-on-toggle.
- **Driver capability probing** (`lpoptions -l`) to show only options a
  printer supports, or to gray out unsupported ones. Later; pairs with #4.
- **Driver-specific color fallbacks** (`ColorModel=Gray`, PPD quirks).
  `print-color-mode` only.
- **Migrating the global `reverse_page_order`** into the per-printer
  store — that's §8 row 3 (#5), a separate change.
- **An app-wide Preferences window** (#17 and friends). This dialog is
  strictly per-printer.
- **Garbage-collecting** `printer_options` entries for printers that no
  longer exist.
- **Persisting dialog geometry** (it's fixed-size).

## 10. Doc maintenance when this ships

Per the repo convention (own spec + appendix + inline ⚠; prune finished
backlog items):

**`specification.md`** — add **Appendix C.5 "Printer options"** (one
paragraph: gear button + per-printer options dialog + summary line;
color default color; fit-to-page **default on, reversing Q3**; links
here as authority). Inline ⚠ asides, bodies untouched:

- §2 "No auto-fit / no scaling" → ⚠ *Changed — C.5: fit-to-page is a
  per-printer option, default on.*
- §4.1 (printer selection bullet) → ⚠ *Extended — C.5: a gear opens
  per-printer output options; a summary line sits under the picker.*
- §4.2 "Any scaling or fit-to-page" and "Configurable page-reversal,
  flip edge, or back-side rotation" → ⚠ *Reopened — C.5 (fit-to-page)
  and spec_printer_options §8 (page order, rotation roadmap).*
- §7.4 "Scaling — none" row → ⚠ *Changed — C.5.*
- §11 Q3 → ⚠ *Reversed 2026-09 — C.5: fit-to-page default on.*

**`feature_requests.md`:**

- Already done (2026-09-06, when the "normalize to Letter" idea was
  dropped): #18/#19 retitled and pointed at this spec, the "normalize
  every page to Letter" content removed from #19, "media-size
  normalization" struck from the "Note on scope" paragraph, and the
  top-of-queue line updated.
- **On ship:** delete **#18** and **#19** entirely (both shipped via the
  color and fit-to-page options). Keep the numbers.
- **#3, #4, #5, #6, #10** — add a one-line pointer in each: "lands on the
  per-printer options mechanism — see
  [spec_printer_options.md](spec_printer_options.md) §8." Fix any `#18` /
  `#19` cross-references elsewhere to plain text.

**`USER_GUIDE.md`** — short "Printer options" subsection: the gear, the
color choice and the fit-to-page checkbox, that they're saved per
printer, and that the line under the picker is the read-out.

## 11. Build outline

| Piece | Change |
|---|---|
| `musicprinter/printer_options.py` (new) | `Option` dataclass (incl. `kind` / `choices`); `ColorMode` (radio), `FitToPage` (check); `REGISTRY`; `defaults` / `for_printer` / `persist` / `summary_line` / `submit_kwargs`. ~90 lines, no I/O beyond calling `settings.save`. |
| `musicprinter/settings.py` | one new default: `"printer_options": {}`. Nothing else. |
| `musicprinter/printing.py` | `submit(...)` gains `color_mode="color"`; emits `-o print-color-mode=color|monochrome`. `fit_to_page` branch already present. |
| `main.py` `App._build` | shrink printer `OptionMenu` to col 1; add `ttk.Button("⚙")` col 2 → `_open_options`; insert the summary `Label` row under the picker; renumber rows below (+1). |
| `main.py` `App.__init__` | `self.options_summary = tk.StringVar()`; `self._printer_opts = printer_options.for_printer(self.cfg, self.printer.get())`; `_refresh_options_summary()`. |
| `main.py` `App._choose_printer` / `_load_printers` | reload `_printer_opts` for the newly-selected printer; `_refresh_options_summary()`. |
| `main.py` `App._set_state` | disable the gear button unless `state == READY`. |
| `main.py` `App._open_options` / `_refresh_options_summary` (new, ~6 lines) | open `OptionsDialog` with `on_apply=` a handler that does `self._printer_opts = values; printer_options.persist(...); self._refresh_options_summary()`; the summary setter reads `printer_options.summary_line`. |
| `main.py` `App._submit_worker` | `**printer_options.submit_kwargs(self._printer_opts)` into `printing.submit`; extend the `settings.log` line. |
| `main.py` `OptionsDialog(tk.Toplevel)` (new, ~80 lines) | header + one block per `REGISTRY` entry — a `Checkbutton` or a `Radiobutton` group per `spec.kind` — bound to draft vars in `self._vars`, + **Apply**; `transient` + `grab_set` + `WM_DELETE_WINDOW` → `_discard`. `_apply` reads the draft vars, calls `on_apply(values)`, closes; `_discard` just closes. No thread, no queue. |
| `tests/test_printer_options.py` (new) | `summary_line` table ([§4.4](#44-the-summary-line)); `submit_kwargs` maps to the right `lp` keys; `for_printer` coercion + unknown-key drop + missing-key fill. |
| `tests/test_printing.py` | `submit(color_mode="mono", fit_to_page=True, …)` puts `print-color-mode=monochrome` and `fit-to-page` on the command. |
| `tests/test_flow.py` | switch printer → `_printer_opts` reloads; **Apply** in dialog → written under the right queue name and survives a reload; **close without Apply** → stored options and `_printer_opts` unchanged; a run passes the flags into `printing.submit` (assert via the `FakePrinting.submit(**kw)` capture — extend it to record `kw`). |
| `tests/test_settings.py` (or `test_flow`) | `printer_options` nested map round-trips through `save` / `load`; a corrupt inner value falls back to default. |
| `docs/` | Appendix C.5 + inline ⚠ in `specification.md`; prune #18 and #19, cross-ref #3–#6, #10 in `feature_requests.md`; `USER_GUIDE.md` subsection. |

Estimate: one new ~90-line pure module, one new ~80-line dialog, ~25
lines of `App` wiring, ~3 lines in `printing.submit`, one settings
default. No new runtime dependency. No state-machine change (that starts
at §8 row 4).

## 12. Testing

- **Unit — `printer_options`:** `summary_line` for all four
  color×fit combinations matches [§4.4](#44-the-summary-line);
  `submit_kwargs` → `{"color_mode": …, "fit_to_page": …}`; `for_printer`
  fills missing keys, coerces types, drops unknowns.
- **Unit — `printing.submit`:** `color_mode="mono"` ⇒
  `-o print-color-mode=monochrome`; `="color"` ⇒ `=color`;
  `fit_to_page=True` ⇒ `-o fit-to-page`; defaults ⇒ color, no
  `fit-to-page` unless asked.
- **Persistence:** **Apply** → `settings.json` `printer_options[<name>]`
  has the new value; **close without Apply** → file and `_printer_opts`
  unchanged; reload `App` → dialog + summary reflect the last applied
  value; configure printer A as B&W, switch to B (defaults), switch back
  to A → B&W restored.
- **Flow:** `_submit_worker` passes the current printer's options into
  `printing.submit` on both passes and on the single-pass path; the
  gear is disabled while a run is active.
- **Headless GUI:** `OptionsDialog` builds, renders each `REGISTRY` entry
  per its `kind` (Checkbutton, or a Radiobutton group) with the right
  initial selection; changing a control updates only the draft; **Apply**
  fires `on_apply` with the draft dict and dismisses; the close box
  dismisses **without** firing `on_apply`.

## 13. Resolved decisions (2026-09-06)

1. **Color control — radio, and store presentation on the descriptor.**
   Color / Black & white is a two-button radio group, not a checkbox.
   `Option` carries a `kind` field (`"check"` / `"radio"` / `"choice"`)
   so each option owns how it renders ([§4.3](#43-the-option-registry));
   the dialog switches on it.
2. **Commit model — Apply only.** The dialog edits a local draft;
   **Apply** is the sole commit (write `_printer_opts`, persist, refresh
   the summary line, close). Closing any other way discards the draft and
   leaves the printer's options unchanged. Not persist-on-toggle.
3. **Color option — `print-color-mode` only for v1.** `ColorModel=…` /
   PPD-specific fallbacks are not attempted; revisit only if a real
   printer needs it.
4. **fit-to-page default ON.** Confirmed — reverses [specification.md
   Q3](specification.md#11-resolved-decisions), matching the request
   ("resize to fit — default, selected"). Recorded via the §10 asides.
5. **Summary line — "Options: " prefix, colon, comma-separated tokens.**
   Small font, muted / modest contrast, advisory only — it is not the
   focus of the window ([§4.1](#41-where-it-lives-on-the-main-window)).
6. **Page-size normalization — dropped.** `fit-to-page` is enough; the
   "normalize every page to Letter" idea is off the roadmap entirely
   ([§9](#9-non-goals)), not a later option.
7. **Migrate `reverse_page_order` — keep it simple, do it with #5.** The
   global stays for now; §8 row 3 folds it into the per-printer store.
   Merge options into one dialog block where it reads better.
8. **Gear glyph.** `⚙` (U+2699); fall back to a text `Options…` button if
   it renders badly on aqua Tk 9.
9. **Summary line is not clickable.** Advisory text only. The gear is the
   one and only way into the dialog.

Nothing open; §4 (the mechanism) and §5 (the two options) are ready to
build.
