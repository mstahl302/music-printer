# Feature Spec — Batch / Set-list Printing

**Feature:** #2 in [feature_requests.md](feature_requests.md)
**Status:** DRAFT — for review. Not approved, not scheduled.
**Date:** 2026-09-01
**Companion artifact:** <https://claude.ai/code/artifact/c0981c44-4fc5-4f34-bce0-ffac9b3aefef>
— mark it up line by line there; this file stays the source of truth and is kept in sync.

---

## 1. Summary

Select several PDFs, put them in performance order, preview the combined
plan, and print the whole set as **one** two-pass job with **one** flip —
instead of running the app once per song. Each song is padded so it
starts on the front of a fresh sheet, so the finished stack can be split
back into individual songs.

## 2. Problem

A choir folder or a recital is a *set* — 5 to 15 songs sung in a fixed
order. Today each one is a separate trip through the app: pick file,
preview, Start, flip, done, repeat. Fifteen flips, fifteen chances to
misfeed the tray. And there's no single "this is what the whole night
costs in paper" number.

## 3. Concepts

- **Set list** — an ordered list of PDF files.
- **Front-facing rule** — every song must begin on a sheet *front* (an
  odd page in the combined sequence), so a reader can lift out "just
  song 4" without it starting mid-sheet.
- **Per-song even padding** — to satisfy the rule, each song's effective
  page count (after cover strip) is padded with a blank up to an **even**
  number. A song that's already even gets no blank. This is stricter than
  the single-file rule in
  [specification.md §7.2](specification.md#72-page-set-computation), which
  only pads when the two passes would otherwise differ by a sheet.
- **Combined two-pass** — all songs are concatenated (with their pad
  blanks) into one page sequence; that sequence gets the ordinary
  even/odd split; the app prints one EVEN mega-PDF and one ODD mega-PDF
  with a single flip between, through the guided dialog (feature #1).
- **Cover strip** — the Smart / Always / Don't-remove choice is **global**
  for the set. Per-file overrides are feature #12, out of scope here.

## 4. Page-planning math

```
build_batch_plan(files, mode, threshold):
    songs = []
    for f in files:
        n_src, encrypted = inspect(f)
        if encrypted or n_src == 0:
            record an error for f; exclude it from the run
            continue
        cover  = detect_cover(f, mode, threshold)      # may be None
        n_eff  = n_src - (len(cover.pages) if cover else 0)
        padded = n_eff + (n_eff % 2)                    # -> even
        songs.append(Song(f, n_src, cover, n_eff, padded))

    total   = sum(s.padded for s in songs)             # always even
    passes  = plan_passes(total)                       # no extra global pad
    layout  = build_batch_layout([s.padded for s in songs], [s.n_eff for s in songs])
    # layout[g] for global page g (1-based) is either
    #   (song_index, source_page)   or   BLANK(song_index)
```

Because every song's `padded` length is even, each song starts at an odd
global index (front-facing ✓), the total is even (no global pad needed),
and any per-song blank lands on an **even** global page — so it prints in
pass 1 and ends up as the *back* of that song's last real page.

### Worked example

| Song | eff. pages | padded | global range |
|---|---|---|---|
| A | 3 | 4 | g1–g4  (a1, a2, a3, **blank**) |
| B | 4 | 4 | g5–g8  (b1, b2, b3, b4) |
| C | 5 | 6 | g9–g14 (c1 … c5, **blank**) |

- **Pass 1 (even g2,4,6,8,10,12,14):** a2, blank, b2, b4, c2, c4, blank — 7 sheets
- **Pass 2 (odd g1,3,5,7,9,11,13):** a1, a3, b1, b3, c1, c3, c5 — 7 sheets

After printing both passes and the one flip: A(1,2,3,·) · B(1,2,3,4) ·
C(1,2,3,4,5,·), every song starting on a sheet front.

## 5. User experience

### 5.1 Building the set

A **Set list window** (opened from a "Print a set…" button on the main
window — **open question 1**):

- A reorderable list. Each row: position, filename, `pages 7 → 6`
  (source → effective), sheet contribution, a status glyph
  (✓ / ⚠ can't open / 🔒 encrypted), a remove (×).
- **Add PDFs…** (multi-select). Reorder with ↑ / ↓ buttons
  (drag-and-drop is **open question 3**).
- Footer: totals — `6 songs · 34 music pages · 18 sheets` — and the
  shared **Strip Cover Sheet** dropdown.
- **Preview & Print →**.

### 5.2 Combined plan preview

One block per song, scrollable:

- post-strip page-1 thumbnail
- filename · `pages 1–6` · cover line (`Musicnotes cover removed (0.97)`
  / `no cover`) · `+1 blank` when padded

Summary bar: `Total 18 sheets · Pass 1: 18 (even + 3 song blanks) ·
flip · Pass 2: 18 (odd)`. **Start**.

### 5.3 Running

Identical to a single file, through the guided run dialog (feature #1):
"Printing — pass 1 of 2 · 6 songs · even pages", flip, pass 2, done.
Cancel semantics unchanged.

## 6. Visual mockups

See the companion artifact. Text sketch of the set-list window:

```
┌─ Set list ─────────────────────────────────────────────────┐
│  Strip Cover Sheet:  [ Smart Strip (remove if detected) ▾ ] │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1  Along the Way.pdf          7→6   3 sheets   ✓    ↑↓ ×│ │
│  │ 2  Best Part.pdf              6→6   3 sheets   ✓    ↑↓ ×│ │
│  │ 3  Willkommen.pdf            10→9   5 sheets   ✓    ↑↓ ×│ │
│  │ 4  scan_old.pdf                 —   —          ⚠    ↑↓ ×│ │
│  └────────────────────────────────────────────────────────┘ │
│  [ Add PDFs… ]              3 songs · 21 pages · 11 sheets   │
│                                     [ Preview & Print → ]   │
└────────────────────────────────────────────────────────────┘
```

## 7. Build outline

| Piece | Change |
|---|---|
| `batchplan.py` (new, pure) | `Song`, `BatchPlan`, `build_batch_layout(padded_lens, eff_lens) -> list[GlobalPage]` where `GlobalPage` is `(song_idx, src_page)` or `BLANK(song_idx)`. Unit-tested like `duplex.py`. |
| `jobs.py` | `build_batch_plan(files, mode, threshold) -> BatchPlan` (inspect + `detect_cover` per file); `build_batch_pass_pdf(plan, which, out_dir)` walks the layout, opening each source once. |
| `duplex.py` | unchanged — `plan_passes(total)` is reused as-is for the combined sequence. |
| `main.py` | new `batch_plan` alongside `plan`; a `SetListWindow(tk.Toplevel)`; `_begin_pass` builds batch pass PDFs when a batch is active; run-dialog copy switches to "N songs". |
| reuses | `plan_passes`, `printing.*`, cover detection, the guided dialog (#1), the thumbnail renderer. |
| `tests/` | `test_batchplan.py` (layout math); extend `test_flow.py` with a batch run. |

Feature #1 (guided dialog) is a soft prerequisite — batch runs want the
consolidated progress/flip UI. Could ship on the current inline UI, but
#1 first is the sensible order.

## 8. Open questions

1. **Entry point** — a separate "Print a set…" button, or a batch/single
   toggle in the main window?
2. **Add folder** (all PDFs in a chosen folder) in v1, or files-only?
3. **Reorder** — ↑/↓ buttons (easy) to start, drag-and-drop later?
4. **A file that won't open** — skip it from the run with a warning
   (proposed), or block Start until it's removed?
5. **Thumbnails in the preview for a big set** — render all up front, or
   lazily / cap at N?
6. **Paper warning threshold** — warn above some sheet count before a big
   run?
7. Confirm **saved set-lists** (feature #11) and **per-song cover
   override** (feature #12) stay out of scope for this spec.
8. Should a **1-song "batch"** just fall through to the normal single-file
   flow?
