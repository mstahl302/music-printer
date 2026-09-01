# Music Printer — Feature Requests

**Status:** BACKLOG — ideas and requests, not yet scheduled or spec'd.
**Date:** 2026-09-01
**Owner:** markstahl

This is a running list of ideas for after v1, roughly ordered by priority
within each section. Nothing here is designed yet — when an item is picked
up, it gets its own design pass (and, where it touches printing behavior,
an update to [specification.md](specification.md)).

> **Note on scope:** several items below (duplex mode, back-side rotation,
> full per-printer page-order handling) revisit decisions
> [specification.md §4.2](specification.md#42-out-of-scope--non-goals-v1)
> and [§7.4](specification.md#74-printer-assumptions) that were originally
> fixed. Page order has already been reopened (it's a settings-file value
> now — see #4). That's fine — this doc is where "maybe later" lives — but
> when one of these is actioned, the spec needs a matching revision, not a
> quiet contradiction.

---

## Requested features

### 1. Batch / set-list printing

Let the user select **multiple PDFs**, arrange them in set-list order (the
order a choir or worship service will actually sing them), preview the
combined plan, and print the whole set as one guided two-pass job instead
of running the app once per song.

The key correctness requirement: **each song must start on a front-facing
page**, so the printed stack can be split back into individual songs (or
handed out mid-packet) without hunting for where one ends and the next
begins. That means each song's own effective page count gets padded to
*even* before concatenation (not just when the file's own count is odd),
so the next song always lands back on an odd (front) position — a
generalization of the single-file blank-pad rule in
[§7.2](specification.md#72-page-set-computation). The preview needs to
show the plan for *every* file in the set, not just a single thumbnail,
including a **running total of sheets across the whole batch** so the
user knows the total paper cost before committing to a long run.

**Value:** this is the actual real-world use case for a choir member or
accompanist — printing an entire Sunday's or a whole recital's worth of
music as one packet, in performance order, in one sitting instead of N
manual runs through the app, with no surprise about how much paper it'll
take.

### 2. Extended printer-setup dialog

A secondary "Printer Setup…" window, off the main flow, that holds the
printer-behavior toggles below (duplex capability, page order, back-side
rotation) plus anything else that's set once per printer and rarely
touched again.

**Value:** keeps the main window to its current "nothing fancy" shape
(printer, file, cover mode, Start) for the common case, while giving the
option to configure or fix printer-specific behavior without cluttering
the everyday screen.

### 3. Detect/select true duplex support

Let the user mark a printer as **capable of real double-sided printing**
and, when set, skip the two-pass-plus-flip workflow entirely: send one job
with the OS duplex option (`lp -o sides=two-sided-long-edge` /
`two-sided-short-edge`) and be done.

**Value:** the whole two-pass design exists to work around a printer that
*can't* duplex. For anyone whose printer actually can, this is strictly
simpler, faster (one job, no waiting, no flip), and removes a whole class
of mid-flip cancel/error states. Likely worth pairing with CUPS capability
probing (`lpoptions -l`) so the app can suggest the right answer instead of
asking the user to know it.

### 4. Page order as a first-class, per-printer setting

Partly done: page order is now controlled by `reverse_page_order` in the
settings file (default on), applied via `lp -o outputorder=reverse` — see
[specification.md §7.4](specification.md#74-printer-assumptions). What's
left: scope it **per printer** (not one global value), expose it in the
extended setup dialog (#2), and have the welcome flow (#6) derive it from
a test print instead of making the user guess.

**Value:** the settings-file toggle already unblocks other printers; this
turns it into something a non-technical user can actually find and set,
and something that survives switching between two printers.

### 5. Configurable 180° rotation on pass 2

Add back `rotate_back_side_180` as a per-printer setting: rotate every
page in the second pass 180° before printing.

**Value:** the correct value depends on exactly how a person physically
flips the stack (short-edge vs. long-edge, and which way). The current
build assumes one specific flip convention; this setting is what makes a
*different* flip convention produce right-side-up backs instead of upside
down.

### 6. Welcome / calibration flow

A first-run wizard that walks a new user through printer setup instead of
asking them to know abstract facts about it: pick a printer, print a small
labelled test sheet (e.g. 4 numbered pages), and answer plain questions
about what came out ("Is page 2 on top or on the bottom of the stack?").
From the answers, derive #3–#5 automatically. Optionally, have the user
physically practice the flip once, with the app confirming the result
before declaring the printer "ready."

**Value:** almost nobody knows offhand whether their printer "reverses
output" or which duplex option their driver exposes — that's exactly the
knowledge this app currently assumes the user (originally, just the
owner) already has. A guided, experiential calibration turns an
unanswerable technical question into "does this look right?", and doubles
as an end-to-end smoke test that printing works at all before someone
commits a real piece of music to it.

### 7. Export to two print-ready PDFs (FIRST / SECOND)

Instead of sending straight to a printer, save the two-pass plan as **two
separate files** — `<name>-FIRST.pdf` (the even/pass-1 pages, with any
blank pad) and `<name>-SECOND.pdf` (the odd/pass-2 pages) — mirroring the
app's own two-pass structure rather than merging everything into one
document.

**Value:** lets someone print at a copy shop, on a printer this Mac can't
reach, or queue the two halves for later: load FIRST, print it, flip the
stack exactly as the app would have prompted, then load SECOND. Applies
equally to a single file or a whole batch (#1) — a batch would export as
one FIRST/SECOND pair covering the entire set.

### 8. Multiple copies as two big passes, one flip

Add a copies count to a print run. Rather than repeating the whole
two-pass-and-flip cycle once per copy (flip after copy 1, print copy 2,
flip again, …), run it as **one EVEN mega-pass covering every copy
back-to-back, a single flip, then one ODD mega-pass covering every
copy** — the same mechanism as batch/set-list printing (#1), just with the
same file repeated N times instead of N different songs, and could reuse
that plumbing directly.

**Value:** for choir handouts or rehearsal copies, this turns "flip 6
times to print 6 copies" into "flip once." Fewer physical touches means
fewer chances to misalign the stack or lose count partway through.

### 9. Guided-print dialog with a louder flip cue

Replace the inline progress strip and flip panel with a dedicated **print
dialog** that opens when the user clicks Start: a busy/progress bar and a
Cancel button, modal to the run so the main window's controls aren't live
mid-job.

When pass 1 finishes and it's time to flip, make the prompt **impossible
to miss**: an audible cue (a ding) plus a large **green "Continue — pages
are flipped" button** in the dialog, with Cancel kept visually secondary
(red). Today the flip prompt is a small framed button
([main.py §flip_frame](../main.py)) that someone looking away from the
screen can easily sit through.

**Value:** the flip is the one point in the run where the app is waiting
on the human, and missing it stalls the job indefinitely. A separate
dialog keeps the run's state in one place (progress, cancel, flip), and a
loud, big-target, colour-coded cue matches how much the moment matters.

---

## Other ideas worth considering

### 10. Printer profiles

Save the duplex/order/rotation settings (#3–#5) **per printer**, not
globally, so someone who prints at home and at a rehearsal hall doesn't
need to redo the welcome flow every time they switch. Natural companion to
#2 and #6.

### 11. Saved set-lists

Once batch printing (#1) exists, let a set of files + order be saved under
a name ("2026-09-06 Service") and reprinted later without reselecting
files — the realistic case is the same weekly rotation with small changes.

### 12. Per-file cover-strip override in a batch

In batch mode, let one file in the set override the global cover-strip
mode (e.g. one song is already stripped, or isn't from Musicnotes at all
and needs "Don't remove" while the rest use Smart).

### 13. More cover-sheet vendors

The detector registry in [cover_signals.md §5](cover_signals.md#5-extensibility)
was built for this: add detectors for Sheet Music Direct, Hal Leonard
Digital, MuseScore.com exports, etc., as real samples turn up.

### 14. Full-document preview, not just page 1

Let the user flip through all pages of the plan preview (or at least the
first couple of pages after the strip), not just the thumbnail of page 1
— catches a bad cover-strip decision or a corrupt/misordered PDF that a
single thumbnail wouldn't reveal.

### 15. Retry a failed pass without restarting

If pass 2 fails partway (paper jam, printer goes offline, printer
disconnects), let the user retry just that pass instead of starting the
whole file over from Start.

### 16. Windows/Linux port

`printing.py` already sits on `lp`/`lpstat`/`cancel`, which exist on Linux
(CUPS) as-is — a Linux build is mostly a packaging exercise. Windows would
need a different print backend (no CUPS), so it's a bigger lift and lower
priority given this started as a personal macOS tool.
