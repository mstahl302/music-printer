# Feature Spec — Guided Print Dialog

**Feature:** #1 in [feature_requests.md](feature_requests.md)
**Status:** DRAFT — for review. Not approved, not scheduled.
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
are *the one forward action for this phase* and *Cancel* — there is no
generic "Close", and the dialog never auto-closes.

### 3.1 Phases

| Phase | Heading | Body | Buttons |
|---|---|---|---|
| Preparing | "Preparing…" | indeterminate bar · "Building pass 1…" | Cancel print |
| Printing pass 1 | "Printing — pass 1 of 2" | indeterminate bar · "Even pages · job `NAME-123`" | Cancel print |
| **Flip** | **"Flip the stack"** | a **print → flip → print** diagram (printer · arrow · a page encircled by two curved arrows · arrow · printer) · "Take the printed pages out, flip the whole stack over the **short edge**, and put them back in the tray." | **Cancel print** (quiet, left) · **Continue — print the back side** (primary, oversized, right) |
| Printing pass 2 | "Printing — pass 2 of 2" | indeterminate bar · "Odd pages · job `NAME-456`" | Cancel print |
| Done | "Done ✓" | "Double-sided copy printed." | **Print another** |
| Job cancelled | "Job cancelled" | pass-1 / flip: (nothing more). pass-2: "Some sheets are printed on one side only, and there may be back-printed sheets still in the printer's feed tray — pull those out before the next job." | **Back to start** |
| Couldn't finish | "Couldn't finish" (alert colour) | the printer/CUPS error | **Back to start** |

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

- **Primary** — the single forward action for the phase: *Continue —
  print the back side* at the flip, *Print another* at Done, *Back to
  start* at a cancelled / failed end. Filled accent, bottom-right, bound
  to `<Return>`.
- **Cancel print** — destructive, quiet: a text button, bottom-left,
  showing the alert colour only on hover / focus. Present during
  Preparing, Printing pass 1, Flip, and Printing pass 2.
- No generic "Close" button anywhere. At a terminal state the dialog
  waits until the user picks the forward action or uses the window's own
  close box.
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
  - during pass 1 → cancel the CUPS job → "Job cancelled" → **Back to
    start** returns the main window to READY.
  - during the flip wait → confirm ("Pass 1 sheets are already
    printed…"); on confirm → "Job cancelled" → Back to start (READY).
  - during pass 2 → cancel the job → "Job cancelled" **with the feed-tray
    note** (§3.1).
- **No retry, ever.** There is no "reprint pass 2" — by the time someone
  cancels mid-run the stack is usually misaligned. Cancel is cancel; the
  message is just "Job cancelled".
- **Printer-paused** warning still fires before the first submit, from the
  main window, before the dialog opens — unchanged.
- **Ending.** At a terminal state the dialog does not auto-close. The
  forward button (**Print another** / **Back to start**) or the window's
  close box dismisses it and returns the main window to its READY / DONE
  state.

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

## 7. Review outcomes (round 1, 2026-09-01)

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

Still to confirm:

1. Exact button wording — flip: **"Continue — print the back side"**;
   Done: **"Print another"**; cancelled / failed: **"Back to start"**.
