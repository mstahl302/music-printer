# Music Printer — Feature Requests

**Status:** BACKLOG — ideas and requests, not yet scheduled or spec'd.
**Date:** 2026-09-01 · updated 2026-09-05
**Owner:** markstahl

Grouped by how badly they're wanted, then roughly by priority within each
group. Nothing here is designed yet — when an item is picked up, it gets
its own design pass. That design lands as its **own** spec file; the
originating spec ([specification.md](specification.md) or a feature spec)
is not rewritten — it gets a short **appendix** noting what changed and
pointing at the new spec.

> **Note on scope:** several items below (duplex mode, back-side rotation,
> full per-printer page-order handling) revisit decisions
> [specification.md §4.2](specification.md#42-out-of-scope--non-goals-v1)
> and [§7.4](specification.md#74-printer-assumptions) that were originally
> fixed. Page order has already been reopened (it's a settings-file value
> now — see #5); color and fit-to-page were reopened as printer options
> ([Appendix C.5](specification.md#c5-printer-options)). That's fine —
> this doc is where "maybe later" lives — but when one of these is
> actioned, the relevant spec gets a matching appendix, not a quiet
> contradiction.

---

## Top priority

**#20 is the current top of the queue** — it's spec'd
([spec_pdf_file_association.md](spec_pdf_file_association.md)), not built.

> This file lists only work that has **not** been done — a finished item
> is deleted, not marked done. Numbers are stable IDs, so a gap just means
> something shipped; what shipped is recorded in the spec files under
> [docs/](.) and their appendices, not here. (#18 print in color and #19
> fit-to-page shipped 2026-09-06 as printer options —
> [spec_printer_options.md](spec_printer_options.md),
> [specification.md Appendix C.5](specification.md#c5-printer-options).)

### 20. Register as a PDF handler ("Open With" association)

> 📄 **Spec:** [spec_pdf_file_association.md](spec_pdf_file_association.md). Not yet built.

Make **Music Printer** appear in a PDF's right-click **Open With**
submenu in Finder and accept the file when chosen — one or more PDFs
selected in Finder and opened with the app land in the main window's
list, exactly as if added through **Add PDFs…**, whether the app was
closed or already running. Three parts: declare `CFBundleDocumentTypes`
(PDF, `Viewer`, `LSHandlerRank: Alternative`) plus a stable
`CFBundleIdentifier` in the bundle; catch the `kAEOpenDocuments` Apple
Event via Tk's `::tk::mac::OpenDocument` (same mechanism as the existing
`tk::mac::Quit`) and route paths into `filelist.add()`; register the
built app with Launch Services (`lsregister`, or move to `/Applications`
and launch once). **Not** the default handler — Preview keeps
double-click; the app only offers itself in the *Open With* submenu.

**Value:** the file is almost always already open in Finder (that's
where a Musicnotes download lands). "Find the app, then find the file"
collapses to one right-click from where the file already is, and
multi-select makes a whole set-list populate in performance order with
no trip through the open panel. For a non-technical user it turns the
tool from something you go *to* into something that's *there* on the
file.

---

## Lower priority

Wanted, but after the items above.

### 3. Extended printer-setup dialog

> Lands on the per-printer options mechanism — the `OptionsDialog` from
> [spec_printer_options.md](spec_printer_options.md) §8. Once page
> order / duplex / rotation are added as options it splits into an
> **Output** and a **Printer behavior** group; no separate window.

A secondary "Printer Setup…" window, off the main flow, that holds the
printer-behavior toggles below (duplex capability, page order, back-side
rotation) plus anything else that's set once per printer and rarely
touched again.

**Value:** keeps the main window to its current "nothing fancy" shape
(printer, file, cover mode, Start) for the common case, while giving the
option to configure or fix printer-specific behavior without cluttering
the everyday screen.

### 4. Detect/select true duplex support

> Lands on the per-printer options mechanism —
> [spec_printer_options.md](spec_printer_options.md) §8 (row 4). Adds a
> `true_duplex` option; when on, `_start_run` sends one `two_sided=True`
> job and skips the flip. The one roadmap item that also touches the
> state machine.

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

### 5. Page order as a first-class, per-printer setting

> Lands on the per-printer options mechanism —
> [spec_printer_options.md](spec_printer_options.md) §8 (row 3). Moves the
> global `reverse_page_order` into `printer_options`, one-time-migrating
> the current global value into the selected printer's entry.

Partly done: page order is now controlled by `reverse_page_order` in the
settings file (default on), applied via `lp -o outputorder=reverse` — see
[specification.md §7.4](specification.md#74-printer-assumptions). What's
left: scope it **per printer** (not one global value), expose it in the
extended setup dialog (#3), and have the welcome flow (#7) derive it from
a test print instead of making the user guess.

**Value:** the settings-file toggle already unblocks other printers; this
turns it into something a non-technical user can actually find and set,
and something that survives switching between two printers.

### 6. Configurable 180° rotation on pass 2

> Lands on the per-printer options mechanism —
> [spec_printer_options.md](spec_printer_options.md) §8 (row 5). A
> `rotate_back_180` option; `build_pass_pdf(plan, "odd", …)` rotates each
> page before writing. Pure `pdfio` change, no state-machine impact.

Add back `rotate_back_side_180` as a per-printer setting: rotate every
page in the second pass 180° before printing.

**Value:** the correct value depends on exactly how a person physically
flips the stack (short-edge vs. long-edge, and which way). The current
build assumes one specific flip convention; this setting is what makes a
*different* flip convention produce right-side-up backs instead of upside
down.

### 7. Welcome / calibration flow

A first-run wizard that walks a new user through printer setup instead of
asking them to know abstract facts about it: pick a printer, print a small
labeled test sheet (e.g. 4 numbered pages), and answer plain questions
about what came out ("Is page 2 on top or on the bottom of the stack?").
From the answers, derive #4–#6 automatically. Optionally, have the user
physically practice the flip once, with the app confirming the result
before declaring the printer "ready."

**Value:** almost nobody knows offhand whether their printer "reverses
output" or which duplex option their driver exposes — that's exactly the
knowledge this app currently assumes the user (originally, just the
owner) already has. A guided, experiential calibration turns an
unanswerable technical question into "does this look right?", and doubles
as an end-to-end smoke test that printing works at all before someone
commits a real piece of music to it.

### 8. Export to two print-ready PDFs (FIRST / SECOND)

Instead of sending straight to a printer, save the two-pass plan as **two
separate files** — `<name>-FIRST.pdf` (the even/pass-1 pages, with any
blank pad) and `<name>-SECOND.pdf` (the odd/pass-2 pages) — mirroring the
app's own two-pass structure rather than merging everything into one
document.

**Value:** lets someone print at a copy shop, on a printer this Mac can't
reach, or queue the two halves for later: load FIRST, print it, flip the
stack exactly as the app would have prompted, then load SECOND. Applies
equally to a single file or a whole set-list — a set-list would export as
one FIRST/SECOND pair covering the entire set.

### 9. Multiple copies as two big passes, one flip

Add a copies count to a print run. Rather than repeating the whole
two-pass-and-flip cycle once per copy (flip after copy 1, print copy 2,
flip again, …), run it as **one EVEN mega-pass covering every copy
back-to-back, a single flip, then one ODD mega-pass covering every
copy** — the same mechanism as set-list printing, just with the same file
repeated N times instead of N different songs, and could reuse that
plumbing directly.

**Value:** for choir handouts or rehearsal copies, this turns "flip 6
times to print 6 copies" into "flip once." Fewer physical touches means
fewer chances to misalign the stack or lose count partway through.

---

## Ideas

Not committed to — captured so they're not lost.

### 10. Printer profiles

> Mostly delivered by the per-printer options mechanism —
> [spec_printer_options.md](spec_printer_options.md) §4.5. Options are
> already keyed by CUPS queue name in `settings.json` → `printer_options`;
> once #4–#6 are options, this is done for those settings.

Save the duplex/order/rotation settings (#4–#6) **per printer**, not
globally, so someone who prints at home and at a rehearsal hall doesn't
need to redo the welcome flow every time they switch. Natural companion to
#3 and #7.

### 11. Saved set-lists

Set-list printing exists now; let a set of files + order be saved under a
name ("2026-09-06 Service") and reprinted later without reselecting
files — the realistic case is the same weekly rotation with small changes.

### 12. Per-file cover-strip override in a batch

In batch mode, let one file in the set override the global cover-strip
mode (e.g. one song is already stripped, or isn't from Musicnotes at all
and needs "Don't remove" while the rest use Smart).

The global control now lives on the preview dialog and re-plans the
thumbnails live ([spec_preview_strip_control.md](spec_preview_strip_control.md));
that spec was written as the first step toward this per-file version —
`build_plan` would take a per-file mode map instead of one `strip_mode`.

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

> Round-1 review of the guided-print-dialog spec rejected retry *after a
> user cancel* — by then the stack is usually misaligned. Retry after a
> *hardware* failure (jam, offline), caught before any sheet is
> mishandled, may still be worth it — revisit if it comes up.

### 16. Windows/Linux port

`printing.py` already sits on `lp`/`lpstat`/`cancel`, which exist on Linux
(CUPS) as-is — a Linux build is mostly a packaging exercise. Windows would
need a different print backend (no CUPS), so it's a bigger lift and lower
priority given this started as a personal macOS tool.

### 17. Dock-icon attention bounce

When the run dialog reaches the flip step, bounce the app's Dock icon
(`NSApp.requestUserAttention_(NSCriticalRequest)`) in addition to the
sound and window-raise. Needs PyObjC (`pyobjc-framework-Cocoa`). Split out
of the guided-print-dialog spec in round-1 review as "not important".
