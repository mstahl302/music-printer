# Music Printer — Specification

**Status:** DRAFT — revision 0.2, incorporates review feedback of 2026-09-01. Awaiting final approval.
**Date:** 2026-09-01
**Owner:** markstahl

> Implementation does not begin until this document is marked **APPROVED**.
> All review questions from revision 0.1 are resolved; see
> [§11](#11-resolved-decisions).

---

## 1. Objective

Produce double-sided ("duplex") sheet music on a **simplex** (single-sided)
printer by splitting a PDF into two passes:

1. Print one set of pages.
2. The user removes the stack, flips it (short edge), and re-inserts it
   into the tray.
3. Print the other set onto the blank backs.

The result is a correctly ordered, correctly collated, double-sided copy.

The owner's established manual process — **print EVEN pages, flip, print ODD
pages** — is known to work on their printer and is the process this app
automates.

---

## 2. Background & constraints

- **Printer reverses page order (fixed assumption).** The owner's printer
  emits PDF pages in reverse order, so a job sent as pages `[2, 4, 6]`
  lands in the output tray stacked so that page 2 is on top. Combined with
  a stack flip, EVEN then ODD yields pages in reading order. This is
  **assumed, hard-coded, and not configurable in v1**; see
  [Appendix A](#appendix-a-page-ordering-rationale).
- **Short-edge flip (fixed assumption).** The user flips the stack about
  the short edge and re-inserts it. No back-side rotation is applied — the
  user manages sheet orientation themselves. Also not configurable in v1.
- **Simplex only.** The app never asks the driver for duplex. It manages
  two one-sided jobs and a human flip in between.
- **Sheet music.** Files are portrait or landscape, usually 1–16 pages,
  almost always from Musicnotes.com, sometimes with a vendor **cover
  sheet** as page 1.
- **Odd page counts are common.** When the content has an odd number of
  pages, the EVEN set is one sheet short of the ODD set; the app inserts a
  blank sheet to compensate ([§7.2](#72-page-set-computation)).
- **No auto-fit / no scaling.** Pages print at 100 %.

---

## 3. Definitions

| Term | Meaning |
|---|---|
| **Source PDF** | The file the user selects, as-is on disk. |
| **Cover sheet** | A non-music page (title / license text) inserted by a vendor, always page 1 when present. |
| **Effective pages** | The pages that remain after cover removal, renumbered from 1. All page math below is in effective-page terms. |
| **N** | Count of effective pages. |
| **EVEN set** | Effective pages 2, 4, 6, … ≤ N. |
| **ODD set** | Effective pages 1, 3, 5, … ≤ N. |
| **Pass 1** | The first print job (EVEN set, possibly + blank). |
| **Pass 2** | The second print job (ODD set), printed after the flip. |
| **Sheet** | One physical piece of paper (two sides). |
| **Blank/pad page** | A generated empty page appended to the EVEN set when N is odd. |

---

## 4. Scope

### 4.1 In scope (v1)

- Select a printer (from the system/CUPS list).
- Select one source PDF.
- Choose a cover-strip mode: **none / always / smart** (default **smart**).
- Show a brief **plan preview** including a first-page (post-strip)
  thumbnail ([§5.3](#53-plan-preview)).
- Run the guided two-pass flow with a flip prompt in the middle.
- Track each pass to completion (reusing `musicprinter.printing`).
- Cancel a pass in progress.
- On completion, reset to allow printing another file, keeping the printer
  selection.
- Persist last printer, last strip mode, last folder.

### 4.2 Out of scope / non-goals (v1)

- True driver duplex, booklet imposition, N-up, stapling, folding.
- Copies > 1.
- Arbitrary page-range selection or page reordering by the user.
- Non-PDF inputs.
- Password-protected / encrypted PDFs — refused with a clear message.
- Editing the PDF (rotate, watermark, metadata). The scaffold's
  `process_pdf` rotate / strip-metadata feature and its `core.py` are
  **removed**.
- Any scaling or fit-to-page.
- Configurable page-reversal, flip edge, or back-side rotation — the
  owner's setup (reversing printer, short-edge flip, no rotation) is
  assumed and fixed.

---

## 5. User experience

### 5.1 Main window

A single non-resizable window, top to bottom:

1. **Printer:** dropdown, default = system default printer, shows
   "(default)" and warns inline if the selected printer is paused.
2. **Sheet music (PDF):** "Choose PDF…" button + path label.
3. **Cover sheet:** dropdown — `Don't remove` / `Always remove first page` /
   `Smart (detect)`; default **Smart**.
4. **Plan preview:** a read-only panel with a first-page thumbnail, updated
   whenever the file or mode changes ([§5.3](#53-plan-preview)).
5. **Start** button (enabled only when printer + valid PDF are set).
6. **Status line** + indeterminate progress bar (reused from the current
   app).
7. **Cancel** button (enabled only while a pass is running).

### 5.2 Cover-sheet control

| Mode | Behaviour |
|---|---|
| `none` | Never remove anything. Effective pages = source pages. |
| `always` | Remove exactly page 1. If the source has only 1 page, do nothing and note it in the preview. |
| `smart` (default) | Run cover detectors. Remove page 1 only if a detector matches at or above the confidence threshold. Otherwise keep all pages. Signals and the decision table are in [cover_signals.md](cover_signals.md). |

### 5.3 Plan preview

Deliberately brief. Four things plus a thumbnail — **no per-pass page
lists**:

1. **Sheets of music to print** — effective page count N (after any strip).
2. **Cover handling** — one line: e.g. "Smart: Musicnotes cover detected
   (0.97) — page 1 will be removed", or "Smart: no cover detected — all 6
   pages kept", or "Forced: first page will be removed", or "Cover removal
   off".
3. **First-page thumbnail** — a rendering of what will become effective
   page 1 (i.e. *after* a strip). **Required** — it is the user's visual
   confirmation that a strip did or didn't do the right thing.
4. **Sheets of paper to prepare** — `ceil(N / 2)` sheets to load in the
   tray. If N is odd, a note: "(a blank sheet is added automatically on
   the first pass)".

Example rendering:

```
[ thumbnail ]   Sheets of music to print:  6
                Cover: Smart — Musicnotes cover detected (0.97), page 1 removed
                Sheets of paper to prepare: 3
```

```
[ thumbnail ]   Sheets of music to print:  5
                Cover: Smart — no cover detected, all 5 pages kept
                Sheets of paper to prepare: 3  (a blank sheet is added on pass 1)
```

### 5.4 Guided flow (state machine)

```
IDLE ──select printer + PDF──▶ READY
READY ──Start──▶ PRINTING_PASS1
PRINTING_PASS1 ──pass 1 job completes──▶ WAIT_FOR_FLIP
PRINTING_PASS1 ──Cancel / job fails──▶ READY   (nothing more printed)
WAIT_FOR_FLIP ──user clicks "Pages are flipped — continue"──▶ PRINTING_PASS2
WAIT_FOR_FLIP ──Cancel──▶ READY   (warn: pass-1 sheets already printed)
PRINTING_PASS2 ──pass 2 job completes──▶ DONE
PRINTING_PASS2 ──Cancel / job fails──▶ DONE-WITH-ERROR (warn: half-printed sheets)
DONE ──"Print another"──▶ READY   (printer selection kept, file cleared)
```

Single-page special case: if N ≤ 1 (or the EVEN set is empty), skip the
two-pass flow — print the one page directly and go straight to DONE, no
flip prompt.

Screen text:

- **PRINTING_PASS1:** "Printing pass 1 of 2 (even pages)… — job `NAME-123`".
- **WAIT_FOR_FLIP:** a prominent instruction + a single button:
  > Pass 1 is done. Take the printed stack out, flip it about the **short
  > edge**, and put it back in the tray. Then click continue.

  Button: **"Pages are flipped — print pass 2"**.
- **PRINTING_PASS2:** "Printing pass 2 of 2 (odd pages)… — job `NAME-456`".
- **DONE:** "✅ Done — double-sided copy printed." + **"Print another"**.

### 5.5 Cancel & error handling

| Situation | Behaviour |
|---|---|
| Cancel during Pass 1 | Cancel the CUPS job, return to READY. No flip prompt. |
| Cancel during WAIT_FOR_FLIP | Return to READY. Dialog: "Pass 1 sheets are already printed; discard them or restart the file." |
| Cancel during Pass 2 | Cancel the CUPS job, go to DONE-WITH-ERROR. Dialog notes some sheets are half-printed. |
| Selected printer paused/stopped | Same warning as current app before submitting; user may queue anyway. |
| Pass job reports `aborted` | Stop the flow, show the error, do **not** advance to the flip prompt. |
| PDF fails to open / encrypted / 0 pages | Block Start; explain in the preview area. |
| Effective pages ≤ 1 | Single page: print it directly in one pass, skip the flip. |

---

## 6. Functional requirements — overview

Three cooperating pieces, each independently testable:

- **Cover detection** ([§7.1](#71-cover-sheet-detection--removal)) — decides
  whether to drop page 1. Full signal analysis in
  [cover_signals.md](cover_signals.md).
- **Page planning** ([§7.2](#72-page-set-computation)) — pure function: N →
  EVEN list, ODD list, pad flag.
- **Job orchestration** ([§7.3](#73-print-job-construction--submission)) —
  builds per-pass PDFs, submits, tracks, gates on the flip.

---

## 7. Functional requirements — detail

### 7.1 Cover-sheet detection & removal

#### 7.1.1 Goals

- Detect a vendor cover sheet as page 1 and remove it before page planning.
- **Bias toward false negatives.** Wrongly stripping a real first page of
  music is worse than leaving a cover on. `smart` must be conservative;
  the plan-preview thumbnail is the user's checkpoint.
- Be **extensible**: adding support for a new vendor's cover = adding one
  detector module, no changes to planning or orchestration.

#### 7.1.2 Architecture

```python
# musicprinter/covers/__init__.py

@dataclass(frozen=True)
class CoverMatch:
    detector: str          # e.g. "musicnotes"
    pages: tuple[int, ...]  # 0-indexed source pages to remove; v1 = (0,)
    confidence: float       # 0.0–1.0
    reason: str             # human-readable, shown in the preview

class CoverDetector(Protocol):
    name: str
    def detect(self, doc) -> CoverMatch | None: ...

REGISTRY: list[CoverDetector] = [MusicnotesCoverDetector()]

def detect_cover(path, mode, *, threshold: float) -> CoverMatch | None:
    """mode ∈ {'none','always','smart'}. Returns the match to apply, or None."""
```

- `none` → return `None`.
- `always` → return `CoverMatch("manual", (0,), 1.0, "always-remove mode")`
  unless the source has ≤ 1 page.
- `smart` → run every detector, keep the highest-confidence `CoverMatch`
  with `confidence >= threshold`; else `None`.
- `threshold` default **0.70**.
- v1 removes at most the single leading page. A detector may *report*
  more, but the orchestrator clamps to page 0 only.

#### 7.1.3 Detection signals

The concrete signals, their measured discrimination on a sample corpus,
the `smart`-mode confidence table, and the plan for adding other vendors
live in **[cover_signals.md](cover_signals.md)**.

Summary: `smart` mode strips page 1 only when **both**

- **A** — page 1 carries no engraved music (zero staff lines, ≤ 2 vector
  draw ops), and
- **B** — page 1 contains Musicnotes cover boilerplate text ("Published
  Under License From", the "Purchasers of this musical file…" notice, or
  the "Unauthorized uses are infringements…" line)

hold (confidence 0.97); or when **A** holds alone with a page of real text
and no full-page image (confidence 0.75). The bare string `musicnotes.com`
is explicitly **not** a signal — it appears on nearly every page.

#### 7.1.4 Effect on page numbering

If a `CoverMatch` is applied, **all downstream logic uses effective
pages**: effective page *i* = source page *i + (pages removed)*. The plan
preview, the thumbnail, the per-pass PDFs, and the blank-pad math are all
in effective-page space.

Worked example — source has 7 pages, cover on page 1, removed:

| Effective page | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Source page | 2 | 3 | 4 | 5 | 6 | 7 |
| Set | ODD | EVEN | ODD | EVEN | ODD | EVEN |

Pass 1 (EVEN) = source pages 3, 5, 7. Pass 2 (ODD) = source pages 2, 4, 6.

### 7.2 Page-set computation

Pure function, no I/O:

```python
@dataclass(frozen=True)
class PrintPlan:
    n_pages: int
    even_pages: tuple[int, ...]   # effective page numbers, ascending
    odd_pages: tuple[int, ...]    # effective page numbers, ascending
    pad_blank: bool               # append one blank to the EVEN pass
    single_pass: bool             # N <= 1 (or EVEN empty): print directly, no flip

def plan_passes(n_pages: int) -> PrintPlan: ...
```

Rules:

1. `even_pages = (2, 4, …, ≤ N)`, `odd_pages = (1, 3, …, ≤ N)` — **ascending,
   never reordered** (the printer's reversal + the flip do the ordering).
2. If `N` is odd → `pad_blank = True` (EVEN pass = even_pages + one blank),
   making sheet counts equal.
3. If `N ≤ 1` → `single_pass = True`; print `odd_pages` (= the one page, or
   nothing) directly, no blank, no flip prompt.

#### Worked examples

| N | EVEN pass | ODD pass | pad? | sheets/pass | notes |
|---|---|---|---|---|---|
| 1 | — | 1 | no | 1 | single pass, no flip |
| 2 | 2 | 1 | no | 1 | |
| 3 | 2 **+blank** | 1, 3 | yes | 2 | |
| 4 | 2, 4 | 1, 3 | no | 2 | |
| 5 | 2, 4 **+blank** | 1, 3, 5 | yes | 3 | |
| 6 | 2, 4, 6 | 1, 3, 5 | no | 3 | |
| 7 | 2, 4, 6 **+blank** | 1, 3, 5, 7 | yes | 4 | |

The physical reason the blank goes **last in the EVEN job** (and why that
lands it as the trailing blank after page N) is traced in
[Appendix A](#appendix-a-page-ordering-rationale).

### 7.3 Print job construction & submission

For each pass the app builds a **temporary PDF** containing exactly that
pass's pages, in list order, then prints that file with the existing
`printing.submit(...)` and tracks it with `printing.job_status(...)`.

- **Why a temp file per pass** rather than `lp -P 2,4,6`: it lets us drop
  the cover, insert the blank, and guarantee page order independent of any
  driver page-range quirk.
- **Blank page:** generated with the same media box as the last EVEN
  effective page (fallback: the first effective page). If page sizes vary
  within the file, the last EVEN page's box wins.
- **Temp files:** created under the OS temp dir, named
  `music-printer-<pid>-pass{1,2}.pdf`, deleted when the flow reaches DONE,
  READY, or on app exit.
- **Submission options:** `title` = `"<file> — pass 1/2 (even)"` etc.;
  no `fit_to_page`; `copies = 1`.
- **Flip gate:** Pass 2 is only built and submitted after Pass 1's job
  reaches a terminal *success* state (`completed` / `gone`) **and** the
  user clicks the continue button. A `gone` result uses the same
  multi-poll grace period as the current app.
- **Completion of the whole flow** = Pass 2 terminal success.

### 7.4 Fixed printer assumptions

Not settings — hard-coded for v1, matching the owner's setup:

| Assumption | Value | Effect |
|---|---|---|
| Printer reverses PDF page order on output | yes | Pass page lists are sent ascending; the printer + flip do the ordering. See [Appendix A](#appendix-a-page-ordering-rationale). |
| Flip edge | short | Wording of the flip instruction only. |
| Back-side rotation | none | Pass-2 pages are sent unrotated. |
| Scaling | none | `lp` gets no `fit-to-page`. |

The only tunable value is `confidence_threshold` (default **0.70**) for
smart cover detection; it lives in the settings file, not the main window.

---

## 8. Non-functional requirements

- **Persistence:** a small JSON file at
  `~/Library/Application Support/Music Printer/settings.json`. Stores last
  printer, last strip mode, last-used folder, and `confidence_threshold`.
  Missing/corrupt file → defaults, no crash.
- **Logging:** append-only log next to the settings file; each pass logs
  the plan, the temp file path, the job id, and the terminal state.
- **Performance:** planning is instant; cover detection + thumbnail render
  on a ≤ 20-page PDF should complete well under 1 s so the preview feels
  live.
- **Offline / no network.**
- **Packaging:** must still build as `Music Printer.app` via `build.sh`.
  New dependency `pymupdf` must be bundled by PyInstaller (its hooks ship
  with `pyinstaller-hooks-contrib`, already installed); expect roughly
  +10–15 MB in the `.app`.
- **Threading:** all subprocess / PDF work off the Tk thread, as in the
  current app; UI updates via the existing queue + `after()` pattern.

---

## 9. Dependencies

| Dependency | Purpose | Status |
|---|---|---|
| `pikepdf` | Already present. Split pages, insert the blank, write the per-pass temp PDFs. | keep |
| `lp` / `lpstat` / `cancel` | Already used. Submit + track + cancel. | keep |
| `pymupdf` | Cover detection (page-1 text, staff-line / vector-draw counts, image rects) **and** rendering the required plan-preview thumbnail. | **add** |

`pypdf` / `pdfminer.six` were considered and rejected: no rendering (so no
thumbnail) and weaker text extraction.

---

## 10. Testing & validation

### 10.1 Unit — page planning

`plan_passes(N)` for `N = 0…8` matches the [§7.2 table](#worked-examples)
exactly, including `pad_blank` and `single_pass`.

### 10.2 Cover-detector corpus validation

Per [cover_signals.md §6](cover_signals.md):

- Enumerate every PDF under Drive `/Music/Vocal/Songs/*`.
- Hand-label cover / no-cover.
- Tune the Musicnotes boilerplate phrases and `confidence_threshold` for
  **zero false strips** and maximum true strips.
- Freeze a small labelled subset as `tests/fixtures/` with expected
  `CoverMatch` output.

An initial 12-file sample is already analysed in cover_signals.md §2–§3;
the numbers there must be re-confirmed on the full corpus before
implementation is considered complete.

### 10.3 Manual print validation (one-time, owner)

A checklist run on the real printer:

1. 4-page file, no cover → assembled 1-2-3-4, correct orientation.
2. 5-page file, no cover → assembled 1-2-3-4-5, trailing blank back.
3. 7-page file with Musicnotes cover, `smart` → cover gone, assembled
   1-2-3-4-5-6.
4. Cancel during Pass 1 → nothing further prints.
5. Cancel during Pass 2 → documented half-printed outcome.
6. Paused printer → warned, can queue.

---

## 11. Resolved decisions

From the revision-0.1 review (2026-09-01):

| # | Question | Decision |
|---|---|---|
| Q1 | Copies > 1 in v1? | Out of scope. |
| Q2 | Remove the scaffold's rotate / strip-metadata feature and `core.py`? | Yes, remove. |
| Q3 | `fit_to_page` default? | No auto-fit; fixed off, print at 100 %. |
| Q4 | First-page thumbnail in the plan preview? | Required. |
| Q5 | Password-protected PDFs? | Out of scope — refuse with a message. |
| Q6 | Effective pages ≤ 1 → single direct pass, no flip? | Yes. |
| Q7 | Smart-strip confidence threshold. | 0.70. |
| Q8 | Ever strip more than one leading page? | No — clamp to page 0. |
| Q9 | Blank pad size when pages within a file differ. | Match the last EVEN page's media box. |
| Q10 | Flip edge. | Short edge — the only option. |
| Q11 | Settings file location. | `~/Library/Application Support/Music Printer/settings.json`. |
| Q12 | PDF library for text / render. | `pymupdf`. |
| Q13 | Run the Drive corpus analysis now? | Done — see [cover_signals.md](cover_signals.md). |
| Q14 | Two-pass model correctness. | Confirmed by owner. |
| — | `printer_reverses_output` / back-side rotation as settings? | Dropped — hard-coded for v1. |

No open questions remain.

---

## Appendix A: page-ordering rationale

This traces *why* "EVEN ascending, then flip, then ODD ascending, blank
last in the EVEN job" produces reading order, given the printer emits PDF
pages last-page-first (a fixed v1 assumption).

Notation: a sheet is written `front / back`; a stack is listed top → bottom.

### A.1 Even count, N = 4 — the owner's known-good case

- EVEN job sent: `[2, 4]`. Printer reverses → images 4, then 2. Output
  stack: `2, 4` (page 2 on top).
- User flips the stack (short edge) → `4, 2` with the blank sides up.
- ODD job sent: `[1, 3]`. Printer reverses → images 3, then 1.
  - Top sheet (carrying 4) gets 3 on its up-face → `4 / 3`.
  - Next sheet (carrying 2) gets 1 → `2 / 1`.
- Final sheets, in reading order: `2 / 1`, `4 / 3` → booklet reads
  1, 2, 3, 4. ✅

### A.2 Odd count, N = 5 — blank last in the EVEN job

- EVEN job sent: `[2, 4, BLANK]`. Printer reverses → images BLANK, 4, 2.
  Output stack: `2, 4, BLANK` (blank at the bottom).
- User flips → `BLANK, 4, 2`, blank sides up.
- ODD job sent: `[1, 3, 5]`. Printer reverses → images 5, 3, 1.
  - Top sheet (the true blank) gets 5 → `5 / (blank)`.
  - Next (carrying 4) gets 3 → `4 / 3`.
  - Next (carrying 2) gets 1 → `2 / 1`.
- Final sheets in reading order: `2 / 1`, `4 / 3`, `5 / (blank)` → booklet
  reads 1, 2, 3, 4, 5, then a blank back. ✅

---

## Appendix B: proposed module layout

```
musicprinter/
  printing.py        # existing: submit / job_status / cancel / printer_state
  covers/
    __init__.py      # CoverDetector protocol, REGISTRY, detect_cover()
    base.py          # shared helpers: staff_line_count, vector_draw_count,
                     #   norm(text), page_has_full_page_image
    musicnotes.py    # MusicnotesCoverDetector: boilerplate phrases + A/B rule
  duplex.py          # plan_passes(N) -> PrintPlan   (pure, unit-tested)
  jobs.py            # build per-pass temp PDFs; run the 2-pass flow
  pdfio.py           # pymupdf/pikepdf wrapper: text, render thumbnail, split, blank
  settings.py        # load/save settings.json
main.py              # Tkinter UI + state machine (§5.4)
docs/specification.md
docs/cover_signals.md
tests/
  test_duplex.py
  test_covers.py
  fixtures/
```

The scaffold's `core.py` is deleted.
