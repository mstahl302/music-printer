# Feature Spec — Guided Print Dialog

**Feature:** #1 in [feature_requests.md](feature_requests.md)
**Status:** DRAFT — for review. Not approved, not scheduled.
**Date:** 2026-09-01
**Companion artifact:** <https://claude.ai/code/artifact/567bce24-6513-414a-9d9b-2d051a729307>
— mark it up line by line there; this file stays the source of truth and is kept in sync.

---

## 1. Summary

Move the whole print run — progress, cancel, and the flip prompt — out of
the main window and into a **modal run dialog** that opens on Start. Make
the flip moment, the one point where the app is blocked waiting on the
person, impossible to miss: a large heading, a short-edge flip diagram, a
full-width primary button, and an audible cue.

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
`grab_set` (modal), not resizable, no minimise button. It owns the run
from Start to a terminal state.

Title bar: `Printing — Along the Way.pdf` (single file) /
`Printing — 6 songs` (batch, feature #2).

The body swaps by phase. Layout is constant: **heading**, **body area**
(bar or diagram + text), **button row** (destructive left, primary
right).

### 3.1 Phases

| Phase | Heading | Body | Buttons |
|---|---|---|---|
| Preparing | "Preparing…" | indeterminate bar · "Building pass 1…" | Cancel |
| Printing pass 1 | "Printing — pass 1 of 2" | indeterminate bar · "Even pages · job `NAME-123`" | Cancel print |
| **Flip** | **"Flip the stack"** | short-edge flip diagram · "Take the printed pages out, flip the whole stack over the **short edge**, and put them back in the tray." | **Cancel print** (quiet, left) · **Done — pages are flipped** (primary, full-width-ish, right) |
| Printing pass 2 | "Printing — pass 2 of 2" | indeterminate bar · "Odd pages · job `NAME-456`" | Cancel print |
| Done | "Done" ✓ | "Double-sided copy printed." | Close |
| Stopped / failed | "Cancelled" / "Couldn't finish" (in the alert colour) | the reason | Close |

Single-page jobs (no flip) run Preparing → Printing → Done.

### 3.2 The flip cue

On entering the **Flip** phase:

1. **Sound.** Play a macOS system sound via `afplay` in a subprocess
   (no dependency), e.g. `/System/Library/Sounds/Glass.aiff`. Fall back
   to `Tk.bell()` if `afplay` isn't runnable. Gated by a new setting
   `flip_sound` (default **on**).
2. **Raise.** `dialog.lift()`, briefly set `-topmost`, `focus_force()` so
   the dialog comes forward if it was buried.
3. **Visual.** Heading in the alert/amber colour, the flip diagram, and
   the primary button rendered large and filled.

Dock-icon bounce (`NSApp.requestUserAttention_`) is the natural next
step but needs PyObjC — **open question 4**, deferred by default.

### 3.3 Buttons and colour

- **Primary** ("Done — pages are flipped", "Close"): filled, accent
  colour, bottom-right, is the default (`<Return>` bound).
- **Destructive** ("Cancel print"): quiet — text or outline button,
  bottom-left, in the alert colour only on hover/focus.
- Confirms for destructive actions stay as today (§4).

## 4. Behaviour

The dialog is a view onto the existing state machine
([specification.md §5.4](specification.md#54-guided-flow-state-machine)).
`READY → PRINTING_PASS1 → WAIT_FOR_FLIP → PRINTING_PASS2 → DONE` is
unchanged; the dialog just renders whichever state the app is in.

- **Modal scope.** While the dialog is open the main window can't be
  touched. It's already fully disabled mid-run today; the dialog makes
  "you're in a run" unambiguous and consolidates progress + cancel + flip.
- **Cancel** — semantics unchanged from
  [specification.md §5.5](specification.md#55-cancel--error-handling):
  - during pass 1 → cancel the CUPS job, close dialog, main window back to
    READY.
  - during the flip wait → confirm ("Pass 1 sheets are already printed…"),
    then close to READY.
  - during pass 2 → cancel the job, dialog shows "Cancelled" with the
    half-printed-sheets note, Close.
- **Printer paused** warning still fires before the first submit (from the
  main window, before the dialog opens) — unchanged.
- **Close** (from Done / Stopped / failed) destroys the dialog,
  `grab_release`, main window shows its DONE / READY state with "Print
  another".

## 5. Visual mockups

See the companion artifact for rendered mockups of all six phases. Text
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
│   Flip the stack                        ⟳           │
│                                    ┌────────┐        │
│   Take the printed pages out,      │ 4 3 2  │ short  │
│   flip the whole stack over the    │  ▭ ▭ ▭ │ edge   │
│   SHORT edge, and put them back    └────────┘  ↕     │
│   in the tray.                                       │
│                                                     │
│   [ Cancel print ]      [  Done — pages are flipped ]│
└─────────────────────────────────────────────────────┘
```

## 6. Build outline

| Piece | Change |
|---|---|
| `rundialog.py` (new) | `RunDialog(tk.Toplevel)` — holds heading, body area, bar, flip diagram, button row; a `show_phase(name, **text)` method. |
| `main.py` | `progress`, `status`, `flip_frame`, `cancel_btn` move off the main window. `_begin_pass` / `_poll_job` / `_finish_pass_*` / `_cancel` keep their logic but call `self.dialog.show_phase(...)` instead of poking main-window widgets. `_start` creates + shows the dialog; terminal states close it. |
| state machine | unchanged. |
| sound | `_play_flip_cue()` → `subprocess.Popen(["afplay", sound])`, fallback `self.bell()`; gated by `settings["flip_sound"]`. |
| `settings.py` | new key `flip_sound` (bool, default `true`); maybe `flip_sound_file`. |
| `tests/test_flow.py` | still drives `app._start()` / `app.state`; add assertions that `app.dialog` exists and reports the right phase. Moderate churn, no new test infra. |

Estimated: one new ~150-line file, ~40 lines moved in `main.py`, ~15 new.
No new runtime dependency (unless Dock-bounce is pulled in — see Q4).

## 7. Open questions

1. **Sound choice + default.** Which system sound (`Glass`, `Ping`,
   `Hero`, `Submarine`)? Ship with `flip_sound` on or off?
2. **Mirror a status line in the main window** too, or dialog-only?
3. **Auto-close on Done** after ~3 s, or always wait for Close?
4. **Dock-icon bounce** — worth adding PyObjC for
   `requestUserAttention_`, or is sound + window-raise enough for v1?
5. **Truly modal (`grab_set`)** vs. just always-on-top? Modal blocks the
   main window entirely — fine, since there's nothing to do there mid-run,
   but confirm.
6. Should **Cancel during pass 2** also offer "reprint pass 2" (ties to
   feature #15, retry a failed pass)?
