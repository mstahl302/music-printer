# Feature Spec — Strip Control on the Preview Dialog

**Feature:** first concrete step toward **#12 — per-file cover-strip
override in a batch** in [feature_requests.md](feature_requests.md); shares
ground with **#14 — full-document preview**. Not itself a backlog entry —
it was spec'd and built directly.
**Status:** IMPLEMENTED — built 2026-09-05.
**Date:** 2026-09-05

> Reconciliation with the earlier specs is by appendix, not by rewriting
> them:
> [spec_batch_printing.md §A.1](spec_batch_printing.md#a1-strip-control-moved-to-the-preview-dialog)
> and
> [specification.md §C.3](specification.md#c3-live-strip-cover-control-on-the-preview-dialog),
> plus inline ⚠ asides at the affected points in those specs. This spec is
> the authority for the strip control on the preview dialog.

---

## 1. Summary

Take the **Strip Cover Sheet** control off the main window and put it in
the **Preview dialog**, where the pages it acts on are actually visible.
Make it **live**: changing it re-runs cover detection and the plan, and
the dialog's thumbnails, "cover removed" chips, per-file page/sheet
counts, and total sheet count all update in place — no reopen.

It stays a **single global option** for now (one setting for the whole
set, exactly as today). Per-document overrides are the next step and are
explicitly out of scope here (§6).

## 2. Problem

Today ([main.py](../main.py) `_build`, row 2) the strip mode is a
`ttk.OptionMenu` on the main window, sandwiched between the printer picker
and the file list:

- It sits next to controls it has nothing to do with (which printer, which
  files), at the same weight, so it reads as "more setup" rather than "a
  decision about these documents".
- Its effect is invisible from where it lives. You pick a mode, then open
  Preview to find out what it did. If the guess is wrong you close the
  dialog, change the menu, reopen. The feedback loop crosses a window
  boundary.
- It offers one answer for the whole set even though "strip" is really a
  per-document judgement — some files in a set-list are already stripped,
  or aren't from a store that ships a cover at all (#12).

The Preview dialog already renders the exact thing the control governs: a
first-page thumbnail per file and a pink **cover removed** chip on the
files where a cover was detected. That is where the control belongs, and
where changing it should show its effect immediately.

## 3. Design

### 3.1 The control

A `ttk.OptionMenu` — same three labels, same `COVER_MODES` mapping as
today:

| Label | mode |
|---|---|
| Always Remove First Page | `always` |
| Don't Remove | `none` |
| Smart Strip (remove if detected) | `smart` |

It moves verbatim into `PreviewDialog`, in a **header row above the
thumbnail list**:

```
┌─ Preview ───────────────────────────────────────────┐
│                                                     │
│   Strip cover sheet:  [ Smart Strip (detect) ▾ ]    │   ← new header row
│  ─────────────────────────────────────────────────  │
│   ┌────┐  Along the Way.pdf                          │
│   │ ▢  │  [ cover removed ]  4 pages · 2 sheets      │
│   └────┘                                             │
│   ┌────┐  Blessed Assurance.pdf                      │
│   │ ▢  │  6 pages · 3 sheets                         │
│   └────┘                                             │
│  ─────────────────────────────────────────────────  │
│   Printing requires 5 sheets of paper               │
│   When you're ready, click Start.                   │
│                                     [   Start   ]   │
└─────────────────────────────────────────────────────┘
```

The main window loses row 2 entirely (label + menu) and gets one row
shorter. Printer, file list, Add / Preview, status line are unchanged.

### 3.2 Live recompute

Changing the menu triggers a full replan, off the UI thread (cover
detection opens and rasterises PDFs — it must not block the modal
dialog). The mechanism mirrors `App._recompute` / `_plan_worker`:

1. `_change_mode(label)` — ignore if the mode is unchanged. Otherwise
   store the new mode, bump a `_replan_token`, enter the **busy** state
   (§3.3), and start a daemon thread running
   `jobs.build_plan(self._files, mode, threshold=self._threshold)`.
2. The worker puts `("replan", token, plan)` (or `("replan_err", token,
   msg)`) on the dialog's existing `self._q`.
3. `_pump` — already polling `self._q` for thumbnails — also drains these.
   A result whose `token != self._replan_token` is **dropped** (the user
   clicked again; a later replan is authoritative). The current result
   becomes `self._setplan` and is applied to the widgets (§3.4).

`self._files` is `[e.path for e in setplan.entries]`, captured at
construction. `_preview_ok()` already guarantees every entry is
error-free before the dialog opens, so the file set is fixed for the life
of the dialog — only per-file *effective* page counts, chips, thumbnails,
and totals change. The list of file blocks never grows or shrinks, so
blocks are built once and mutated in place.

### 3.3 Busy state

While a replan is in flight:

- **Start** is disabled (`widgets.Button.set_enabled(False)`) — the plan
  it would hand back is stale.
- The OptionMenu is disabled (`state="disabled"`) so clicks can't stack
  up mid-compute. It re-enables when the result lands.
- The secondary line under the sheet count reads **"Recalculating…"** in
  place of "When you're ready, click Start."

Replans are fast (a handful of PDFs, detection already run once) so this
is usually a sub-second flicker. The token guard, not a debounce, handles
rapid clicking.

### 3.4 What updates on a new plan

For each file block `i`, from the new `SetPlan`:

| Element | Source | Note |
|---|---|---|
| **cover removed** chip | `entry.cover_removed` | shown iff `> 0`; created/destroyed as needed |
| page · sheets line | `entry.n_effective`, `layout.file_sheets(i)` | |
| **thumbnail** | `render_thumbnail_png(path, entry.cover_removed, …)` | re-rendered **only** for files whose `cover_removed` changed vs. the previous plan; those labels drop back to the `"…"` placeholder until the new PNG arrives |
| "Printing requires N sheets" | `setplan.sheets_to_prepare` | |

Thumbnail re-rendering reuses the existing `_render_thumbs` thread +
`_pump` path, with its own `_thumb_token` so a stale render can't paint
over a fresh one. Only changed offsets are enqueued, so switching
`smart → none` on a 3-file set where 2 had covers re-renders 2 thumbs,
not 6.

### 3.5 Persistence

`strip_mode` stays in the settings file and is still written **the moment
the control changes** — same behavior as the current main-window menu,
just from the dialog. `PreviewDialog` takes an `on_mode_change(mode)`
callback; `App` wires it to
`self.cfg["strip_mode"] = mode; settings.save(self.cfg)`.

Consequence: the mode a user picks in Preview is the mode the *next*
Preview opens with, and the mode `App._recompute` uses for the
main-window plan, whether or not they hit Start.

### 3.6 Closing without Start

`PreviewDialog` currently has no Cancel button — it's dismissed with the
window close box, which today just destroys the toplevel. Wire that
through a proper `close()` via `protocol("WM_DELETE_WINDOW", …)` and add
an `on_close` callback. `App` passes a handler that calls
`self._recompute()` so the main-window `self.setplan` is rebuilt against
the (possibly changed) mode. The Start path already installs the fresh
plan via `on_start`, so it does not also need `on_close`.

## 4. Behavior details

- **Modality unchanged.** The dialog keeps its `transient` + `grab_set`.
  The replan worker is a daemon thread; results arrive through the queue
  the dialog already pumps.
- **`single_pass` can flip.** Stripping a cover off a 2-page file makes it
  1 effective page; `none` on a file that was 1 effective page makes it 2.
  `setplan.single_pass` / `sheets_to_prepare` are read from the plan at
  Start, so this just works — the "requires N sheets" line already
  reflects it.
- **Never strips the whole document.** `jobs._inspect_one` already resets
  the match when `removed >= n_src`, so `always` on a 1-page file is a
  no-op and shows no chip.
- **Replan error.** `jobs.build_plan` raising here is near-impossible (the
  files opened cleanly for the first plan) but a detector could throw.
  Handling: revert the OptionMenu to the last good mode, leave the last
  good plan on screen, and show the message in the secondary line
  briefly. No partial plan is ever handed to Start.
- **App shutdown mid-replan.** `App._on_close` already calls the dialog's
  `close()`, which sets `_closing` and cancels the `after` timers; a
  late queue message is dropped because `_pump` bails on `_closing`.

## 5. Build outline

| Piece | Change |
|---|---|
| `main.py` `App._build` | delete the "Strip Cover Sheet:" label + `ttk.OptionMenu` (row 2); rows below shift up. |
| `main.py` `App.__init__` | drop `self.cover_label`. `COVER_MODES` / `MODE_TO_LABEL` / `DEFAULT_COVER_LABEL` stay module-level (now used by `PreviewDialog`). |
| `main.py` `App._set_state` | remove `self.cover_menu.config(state=…)`. |
| `main.py` `App._recompute` | drop the first two lines that copy `self.cover_label` into `cfg`; keep reading `self.cfg["strip_mode"]`. |
| `main.py` `App._open_preview` | pass `threshold=float(self.cfg["confidence_threshold"])`, `on_mode_change=self._persist_strip_mode`, `on_close=self._recompute`. |
| `main.py` `App._persist_strip_mode` (new, ~2 lines) | write `cfg["strip_mode"]` + `settings.save`. |
| `main.py` `PreviewDialog.__init__` | new kwargs `threshold`, `on_mode_change`, `on_close`. Capture `self._files`, `self._mode`, `self._threshold`, `self._replan_token = 0`, `self._thumb_token = 0`. Build the header row with the OptionMenu → `_change_mode`. Split the per-file block build into `_build_blocks()` (once) + `_apply_plan(plan)` (text/chip/count/thumb-kick). `protocol("WM_DELETE_WINDOW", self._dismiss)`. |
| `main.py` `PreviewDialog._change_mode` / `_replan_worker` / `_apply_plan` / `_set_busy` / `_dismiss` (new) | ~50 lines total; `_pump` gains a branch for `("replan", …)` / `("replan_err", …)`. |
| `musicprinter/jobs.py`, `duplex.py`, `covers/*`, `settings.py` | unchanged. `settings.DEFAULTS["strip_mode"]` stays. |
| `tests/test_flow.py` | lines 89 / 94 reference `app.cover_label` — replace with `app.cfg["strip_mode"]` (or just assert printer unchanged). `_app_with` unchanged. |
| `tests/test_preview.py` | add: OptionMenu present in the dialog; `dlg._change_mode("Don't Remove")` then pump → "cover removed" chip gone, per-file count line and "requires N sheets" line updated; `_change_mode` twice in a row → only the last plan is applied (token guard). |
| `docs/` | appendix in `spec_batch_printing.md` and `specification.md`; remove the retired items from `feature_requests.md` (done — see the note at the top of this file). |

Estimate: ~15 lines removed from the main window, ~70 new in
`PreviewDialog`, one new 2-line `App` method, moderate test churn. No new
runtime dependency; no state-machine change.

## 6. Non-goals

- **Per-document strip override (#12).** This spec deliberately keeps one
  global control. It's the enabling step: once the dialog owns the
  control and can replan live, adding a per-row control that overrides the
  global for one file is a contained follow-up (`build_plan` would take a
  per-file mode map instead of one `strip_mode`).
- **Full multi-page preview (#14).** Thumbnails stay first-effective-page
  only.
- **Changing what "strip" means.** Detection, thresholds, the registry,
  the `removed >= n_src` guard — all untouched.
- **A Cancel button in the dialog.** Out of scope beyond wiring the
  window close box through `close()` so `on_close` can fire.

## 7. Resolved decisions (2026-09-05)

1. **Persistence — persist on change.** `strip_mode` is written the moment
   the control changes, matching today's main-window menu. Not provisional
   / commit-on-Start. `on_close → _recompute` keeps the main window
   coherent when the dialog is dismissed without Start.
2. **Placement — header row above the thumbnails** (§3.1 mockup), not the
   bottom bar. It reads as "this governs the list below".
3. **Thumbnails — re-render only changed offsets** (§3.4). Files whose
   `cover_removed` is unchanged between plans keep their existing image;
   no full flash of `"…"` placeholders on every toggle.

Nothing open.
