# Feature Spec — Guided Print Dialog

**Feature:** #1 in [feature_requests.md](feature_requests.md)
**Status:** IMPLEMENTED — shipped 2026-09-01 (rev 2, review round 1 applied).
**Date:** 2026-09-01 · rev 2 (review round 1 applied)
**Companion artifact:** <https://claude.ai/code/artifact/567bce24-6513-414a-9d9b-2d051a729307>
— mark it up line by line there; this file stays the source of truth and is kept in sync.

---

## 1. Summary

Move the whole print run — progress, cancel, and the flip prompt — out of
the main window and into a **truly modal run dialog** that opens on Start.
Make the flip moment, the one point where the app is blocked waiting on
the person, impossible to miss: a large heading, a short-edge flip
diagram, an oversized primary button, and a sound.

Nothing about the two-pass logic or the state machine changes. This is a
presentation change.

## 2. Problem

Today ([main.py](../main.py)):

- Progress bar, status line, the flip panel, and Cancel are all inline in
  the main window, at the same visual weight as the printer/file/mode
  controls above them.
- The flip prompt is a small `LabelFrame` with a normal-sized button. If
  you've walked away from the machine — which is exactly what you do
  during a print — you can sit through it indefinitely. The job just
  waits.
- There's no signal that pass 1 finished other than looking at the screen.

## 3. The run dialog

A `Toplevel` window, centered over the main window, `transient` +
`grab_set` — **truly modal**: while a run is in progress the main window
receives no input at all (§4). Not resizable, no minimise button. It owns
the run from Start to a terminal state and is the only surface — there is
no mirrored status in the main window.

Title bar: `Printing — Along the Way.pdf` (single file) /
`Printing — 6 songs` (batch, feature #2).

The body swaps by phase. Layout is constant: **heading**, **body area**
(bar or diagram + text), **button row**. At every point the only actions
are *Cancel* and *the one forward action for the phase*. During an active
run that forward action is only "Continue" (at the flip). At a terminal
state (Done, cancelled, failed) the single button is **Close**, which
dismisses the dialog. The dialog never auto-closes.

### 3.1 Phases

| Phase | Heading | Body | Buttons |
|---|---|---|---|
| Preparing | "Preparing…" | indeterminate bar · "Building pass 1…" | Cancel print |
| Printing pass 1 | "Printing — pass 1 of 2" | indeterminate bar · "Even pages · job `NAME-123`" | Cancel print |
| **Flip** | **"Flip the stack"** | a **print → flip → print** diagram (printer · arrow · a page encircled by two curved arrows · arrow · printer) · "Take the printed pages out, flip the whole stack over the **short edge**, and put them back in the tray." | **Cancel print** (quiet, left) · **Continue — print the back side** (primary, oversized, right) |
| Printing pass 2 | "Printing — pass 2 of 2" | indeterminate bar · "Odd pages · job `NAME-456`" | Cancel print |
| Done | "Done ✓" | "Double-sided copy printed." | **Close** |
| Job cancelled | "Job cancelled" | pass-1 / flip: (nothing more). pass-2: "Some sheets are printed on one side only, and there may be back-printed sheets still in the printer's feed tray — pull those out before the next job." | **Close** |
| Couldn't finish | "Couldn't finish" (alert colour) | the printer/CUPS error | **Close** |

**Close** at any terminal state just dismisses the dialog window and
returns to the main window (READY, or DONE where its own "Print another"
takes over).

Single-page jobs (no flip) run Preparing → Printing → Done.

The word "Done" is deliberately **not** used on the flip button — the run
isn't finished there, it's continuing to side two.

### 3.2 The flip cue

On entering the **Flip** phase:

1. **Sound.** Always plays (no setting, no off switch). Run
   `afplay /System/Library/Sounds/Ping.aiff` in a subprocess (no
   dependency); fall back to `Tk.bell()` if `afplay` won't run.
2. **Raise.** `dialog.lift()`, briefly set `-topmost`, `focus_force()` so
   the dialog comes forward if it was buried.
3. **Visual.** Heading in the amber alert colour, the flip diagram, and
   the primary button rendered large and filled.

Dock-icon bounce is out of scope for this spec — tracked as an idea in
[feature_requests.md](feature_requests.md).

### 3.3 Buttons and colour

- **Primary** — flat, filled, white text, bottom-right, bound to
  `<Return>`. **Green** *Continue — print the back side* at the flip;
  **blue** **Close** at every terminal state (Done, cancelled, failed) —
  Close just dismisses the dialog.
- **Cancel print** — a flat **red** button, bottom-left. Present during
  Preparing, Printing pass 1, Flip, and Printing pass 2.
- **No "Close" during an active run** — mid-run the only actions are
  Continue (at the flip) and Cancel print. Close appears only once the
  run has reached a terminal state.
- Buttons come from `musicprinter/widgets.py`. `tk.Button` on macOS aqua
  ignores `background` while enabled (shows grey), so `widgets.Button` is
  a `tk.Label` with mouse bindings — `highlightthickness=0` (the grey
  focus border was the culprit) and no `configure` override (call
  `set_enabled(bool)`, not `configure(state=…)`). Green `#2f8f4e`, red
  `#c0392b`, blue `#2b5fb0`; disabled blends 55 % toward white. **The
  main window uses the same set** — *Choose PDF…* and *Start* are blue,
  *Start* fades while disabled.
- The indeterminate progress bar steps every ~55 ms (a bit slower than
  the Tk default) so it reads as working, not frantic.
- Destructive confirmations are unchanged (§4).

## 4. Behaviour

The dialog is a view onto the existing state machine
([specification.md §5.4](specification.md#54-guided-flow-state-machine)).
`READY → PRINTING_PASS1 → WAIT_FOR_FLIP → PRINTING_PASS2 → DONE` is
unchanged; the dialog just renders whichever state the app is in.

- **Truly modal.** The dialog takes a `grab_set`. While a run is in
  progress the main window **cannot be used at all** — not merely
  greyed-out, it receives no clicks or keystrokes. Nothing in the main
  window is relevant mid-run, and there is no status line mirrored there.
- **Cancel** — semantics from
  [specification.md §5.5](specification.md#55-cancel--error-handling):
  - during pass 1 → cancel the CUPS job → "Job cancelled" → **Close**
    returns the main window to READY.
  - during the flip wait → confirm ("Pass 1 sheets are already
    printed…"); on confirm → "Job cancelled" → Close (READY).
  - during pass 2 → cancel the job → "Job cancelled" **with the feed-tray
    note** (§3.1).
- **No retry, ever.** There is no "reprint pass 2" — by the time someone
  cancels mid-run the stack is usually misaligned. Cancel is cancel; the
  message is just "Job cancelled".
- **Printer-paused** warning still fires before the first submit, from the
  main window, before the dialog opens — unchanged.
- **Ending.** At a terminal state the dialog does not auto-close. **Close**
  (or the window's close box) dismisses it and returns to the main window
  in its READY / DONE state — where the main window's own "Print another"
  takes over.

```
State flow (unchanged — the feature is presentation only):

  READY ─Start─▶ PRINTING PASS 1 ─pass 1 done─▶ WAIT FOR FLIP ─"Continue"─▶ PRINTING PASS 2 ─pass 2 done─▶ DONE
                      │                              │                            │
                   cancel                     cancel (pass 1                    cancel
                      ▼                        sheets printed)                     ▼
                   READY ◀───────────────────────────┘                DONE (with feed-tray note)
```

## 5. Visual mockups

See the companion artifact for rendered mockups of every phase. Text
sketch of the two that matter most:

```
┌─ Printing — Along the Way.pdf ──────────────────────┐
│                                                     │
│   Printing — pass 1 of 2                             │
│                                                     │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  (indeterminate)       │
│   Even pages · job Xerox_Phaser…-42                  │
│                                                     │
│   [ Cancel print ]                                  │
└─────────────────────────────────────────────────────┘

┌─ Printing — Along the Way.pdf ──────────────────────┐
│                                                     │
│   Flip the stack                                    │
│                                                     │
│    [printer] ──▶  ( arrows around a page )  ──▶ [printer]
│    print side 1       flip the stack       print side 2
│                                                     │
│   Take the printed pages out, flip the whole stack   │
│   over the SHORT edge, and put them back in the tray.│
│                                                     │
│  [ Cancel print ]   [ Continue — print the back side ]│
└─────────────────────────────────────────────────────┘
```

## 6. Build outline

| Piece | Change |
|---|---|
| `rundialog.py` (new) | `RunDialog(tk.Toplevel)` — heading, body area, bar, flip diagram, button row; a `show_phase(name, **text)` method. One forward button per phase, one Cancel. |
| `main.py` | `progress`, `status`, `flip_frame`, `cancel_btn` move off the main window. `_begin_pass` / `_poll_job` / `_finish_pass_*` / `_cancel` keep their logic but call `self.dialog.show_phase(...)`. `_start` creates + shows the dialog with `grab_set`; terminal states leave it up until the user dismisses it. |
| state machine | unchanged. |
| sound | `_play_flip_cue()` → `subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"])`, fallback `self.bell()`. Always on — no setting. |
| `tests/test_flow.py` | still drives `app._start()` / `app.state`; add assertions that `app.dialog` exists and reports the right phase. Moderate churn, no new test infra. |

Estimate: one new ~150-line file, ~40 lines moved in `main.py`, ~15 new.
No new runtime dependency.

## 7. Review outcomes (2026-09-01)

Resolved:

- **Sound** — always on, no off switch. macOS **Ping**.
- **Main-window status mirror** — none. The main window is fully blocked
  (truly modal) during a run.
- **Auto-close on Done** — no. The dialog waits for the user.
- **Dock-icon bounce** — out of scope here; added to feature_requests.md
  (Ideas).
- **Truly modal (`grab_set`)** — yes.
- **Retry a cancelled pass** — never. Cancel is cancel. A pass-2 cancel
  additionally warns about back-printed sheets left in the feed tray.
- **Button wording** — flip: **"Continue — print the back side"**; every
  terminal state (Done, cancelled, failed): **"Close"**, which just
  dismisses the dialog.
- **Flip diagram** — a *print → flip → print* row: printer, arrow, a page
  encircled by two curved arrows, arrow, printer.
- **Button colour** (post-build polish) — green Continue, red Cancel,
  blue Close; flat filled `tk.Button`s. Progress bar slowed to ~55 ms/step.

Nothing open.
