# Feature Spec — Set-List Printing

**Feature:** #2 in [feature_requests.md](feature_requests.md)
**Status:** APPROVED — implemented (rev 2, approved and built 2026-09-01)
**Date:** 2026-09-01
**Companion artifact:** <https://claude.ai/code/artifact/c0981c44-4fc5-4f34-bce0-ffac9b3aefef>
— mark it up line by line there; this file stays the source of truth and is kept in sync.

> **This replaces the single-file flow.** The app becomes multi-file-native:
> the main window holds a list of one or more PDFs. There is no "batch
> mode" and no single-vs-set toggle — one file is just a list of one. When
> approved, [specification.md §5](specification.md#5-user-experience) needs
> a matching revision.

---

## 1. Summary

The main window holds an ordered **list of PDFs** — one, or a dozen. Add
files, drag them into performance order, hit **Preview**. The preview
dialog shows a first-page thumbnail and a page/sheet line for every file;
**Start** there prints the whole list as **one** two-pass job with **one**
flip, through the run dialog from feature #1. Each file is padded so it
begins on the front of a fresh sheet, so the finished stack pulls apart
into individual songs.

## 2. Problem

A choir folder or a recital is a *set* — 5 to 15 songs in a fixed order.
Today each is a separate trip through the app: pick file, preview, Start,
flip, done, repeat. Fifteen flips, fifteen chances to misfeed the tray,
and no single "this is what the whole night costs in paper" number.

## 3. Concepts

- **The list** — one or more PDF files, in order. The everyday case is
  still a single file; nothing about that gets slower.
- **Front-facing rule** — every file must begin on a sheet *front* (an odd
  page in the combined sequence) so a reader can lift out "just song 4"
  without it starting mid-sheet.
- **Per-file even padding** — to satisfy the rule, every file **except the
  last** is padded with a blank up to an **even** effective length. The
  last file is left as-is; if that makes the grand total odd,
  `plan_passes` absorbs it with its own trailing blank. For a list of one
  this is exactly
  [specification.md §7.2](specification.md#72-page-set-computation) — a
  lone 1-page file still prints in one pass with no flip. One code path.
- **Combined two-pass** — all files are concatenated (with their pad
  blanks) into one page sequence; that sequence gets the ordinary even/odd
  split; the app prints one EVEN mega-PDF and one ODD mega-PDF with a
  single flip, through the run dialog (feature #1).
- **Cover strip** — the Strip Cover Sheet choice is **global** for the
  list. Per-file overrides are feature #12, out of scope.

## 4. Page-planning math

```
build_plan(files, mode, threshold):
    entries = []
    for f in files:
        n_src, encrypted = inspect(f)
        if encrypted or n_src == 0:
            mark f un-openable        # blocks Preview until removed (§5.1)
            continue
        cover  = detect_cover(f, mode, threshold)      # may be None
        n_eff  = n_src - (len(cover.pages) if cover else 0)
        entries.append(Entry(f, n_src, cover, n_eff))

    lens   = [e.n_eff for e in ok(entries)]
    last   = len(lens) - 1
    padded = [n + (n % 2) if i != last else n         # last file: not padded
              for i, n in enumerate(lens)]
    total  = sum(padded)
    passes = plan_passes(total)                        # trailing blank iff total is odd
    layout = build_set_layout(padded, lens)
    # layout[g] for global page g (1-based) is either
    #   (file_index, effective_page)   or   BLANK(file_index)
```

Because every file but the last has an even `padded` length, each file
starts at an odd global index (front-facing ✓). Any per-file blank sits at
the end of that file's block — an **even** global page — so it prints in
pass 1 and becomes the *back* of that file's last real page. If the last
file is odd, `plan_passes` adds one trailing blank to the even pass, which
is the same thing for the last file.

### Worked example

| File | eff. pages | padded | global range |
|---|---|---|---|
| A | 3 | 4 | g1–g4  (a1, a2, a3, **blank**) |
| B | 4 | 4 | g5–g8  (b1, b2, b3, b4) |
| C (last) | 5 | 5 | g9–g13 (c1 … c5) |

Total 13 → `plan_passes(13)` adds one trailing blank to the even pass.

- **Pass 1 (even g2,4,6,8,10,12 + trailing blank):** a2, blank, b2, b4, c2, c4, blank — 7 sheets
- **Pass 2 (odd g1,3,5,7,9,11,13):** a1, a3, b1, b3, c1, c3, c5 — 7 sheets

After both passes and the one flip: A(1,2,3,·) · B(1,2,3,4) ·
C(1,2,3,4,5,·), every file starting on a sheet front — the same result
whether C's trailing blank comes from its own pad or from `plan_passes`.

## 5. User experience

### 5.1 The main window

The main window carries the file list directly — no separate window, no
mode.

- **Strip Cover Sheet** dropdown (global) and **Printer** dropdown, as now.
- **The list.** A bordered box with **alternating white / light-grey
  rows** so it reads as a list even when empty (empty rows carry an "Add
  PDFs to build your set…" hint). Each file row:
  - a **drag handle** (grippy, `⠿`) on the left edge — drag a row up or
    down to reorder.
  - the **filename**, middle-truncated with `…` if long (the extension is
    kept), so the remove control is always visible.
  - `N pages` — the effective page count (after cover strip). A file that
    can't be opened shows **⚠ Can't open this PDF** here instead.
  - a **remove** control at the right edge — a small **red ×**. No "OK"
    checkmark; a row that's fine just shows its page count.
  - No position numbers.
- **Add PDFs…** — a normal open panel with multi-select; appends to the
  list.
- The box shows **6 rows**; beyond that it **scrolls** (scrollbar appears
  only when needed).
- **Preview** button — enabled when the list has at least one file **and
  no un-openable files**. An un-openable file blocks Preview until it is
  removed.

### 5.2 The preview dialog

A separate `Toplevel`, opened by **Preview**. Scrollable. **One block per
file — a first-page thumbnail (post-strip) for every file in the list**;
scroll if there are many.

Each block: the thumbnail, the filename, and a one-line side comment:

> `[cover removed]` · 5 pages · 3 sheets

- `[cover removed]` is a small **coloured chip** (pink). It appears only
  when a cover was actually removed. **No confidence score, ever.**
- When no cover was removed, the line is just `5 pages · 3 sheets`.

At the bottom:

- a whole-set summary line;
- to the left of Start: **"Printing requires _X_ sheets of paper. When
  you're ready, click Start."**
- the **Start** button.

### 5.3 Running

**Start** in the preview dialog **closes the preview** and hands off to
the run dialog from feature #1 — the "printing" view that already exists:

```
Printing — 6 songs
pass 1 of 2 · even pages   →   flip the stack   →   pass 2 of 2 · odd pages   →   Done
```

For a list of one the run-dialog title is the filename, as today. Cancel
semantics are unchanged (feature #1 §4).

## 6. Visual mockups

See the companion artifact. Text sketch of the main-window list:

```
Strip Cover Sheet:  [ Smart Strip (remove if detected) ▾ ]
Printer:            [ Xerox Phaser (Windermere)  (default) ▾ ]

┌──────────────────────────────────────────────────────────┐
│ ⠿  Along the Way.pdf                     6 pages       ⊗ │
│ ⠿  Best Part.pdf                         6 pages       ⊗ │
│ ⠿  Willkommen.pdf                        9 pages       ⊗ │
│ ⠿  scan_old.pdf              ⚠ Can't open this PDF     ⊗ │
│                              ▲ scrolls past ~6 rows      │
└──────────────────────────────────────────────────────────┘
[ Add PDFs… ]                                    [ Preview ]
```

Preview dialog (one block per file):

```
┌─ Preview ────────────────────────────────────────────────┐
│  [thumb]  Along the Way.pdf     (cover removed) 6 pages · 3 sheets │
│  [thumb]  Best Part.pdf                          6 pages · 3 sheets │
│  [thumb]  Willkommen.pdf        (cover removed) 9 pages · 5 sheets │
│                          … scrolls …                     │
│  ────────────────────────────────────────────────────    │
│  Printing requires 11 sheets of paper.                   │
│  When you're ready, click Start.          [   Start   ]  │
└─────────────────────────────────────────────────────────┘
```

## 7. Build outline

| Piece | Change |
|---|---|
| `duplex.py` | add `plan_set(effective_lengths) -> SetLayout` — pad all-but-last to even, concatenate, call `plan_passes(total)`, expose `even_refs()` / `odd_refs()`. A 1-element list equals `plan_passes` exactly. |
| `jobs.py` | `build_plan(files: list[Path], mode, threshold) -> SetPlan` (inspect + `detect_cover` per file, flag un-openable ones). `build_pass_pdf(plan, which, out_dir)` walks the global layout across every source, opening each once. |
| `main.py` | main window gains a scrollable **file-list** widget (rows: drag-handle, name, page count / warning, red ⊗). **Preview** button opens `PreviewDialog(tk.Toplevel)`; its **Start** closes it and calls the existing run-start path. |
| `PreviewDialog` (new) | scrollable list of per-file thumbnail + `[cover removed]` chip + `N pages · M sheets`; summary; "requires X sheets" line; Start. |
| reuses | `plan_passes`, `printing.*`, cover detection, the run dialog (#1), the thumbnail renderer, `widgets.Button`. |
| `tests/` | `test_duplex.py` gains `plan_set` cases; `test_flow.py` gains a multi-file run. |

Feature #1 (the run dialog) is a prerequisite — it is the printing view
this hands off to. It is built.

## 8. Review outcomes (2026-09-01)

- **No modes.** Multi-file is the only mode; one file is a list of one.
  No "Print a set…" button, no toggle.
- **Reorder** — drag by a grip handle on each row (not ↑/↓ buttons).
- **Row controls** — a red circle-X (`⊗`) to remove; no "OK" checkmark.
- **Un-openable file** — shows a warning in place of the page count and
  **blocks Preview until removed**.
- **Long lists** — show ~6 rows, then scroll.
- **Preview thumbnails** — render the first page of **every** file; scroll
  if needed. No lazy-loading, no cap.
- **Per-file side comment** — `[cover removed]` (pink chip, only when a
  cover was removed) · `N pages` · `M sheets`. No confidence score.
- **Preview is its own dialog**; Start there swaps it for the run dialog.
- **"Requires X sheets of paper"** line sits to the left of Start.
- **Add-folder**, **paper-count threshold warning**, **saved set-lists**
  (#11), **per-file cover override** (#12) — all out of scope.

Nothing open.

> Note: comment 9a57fb6d referenced an attached image of the intended
> file-list look. This spec is written from the text description; if the
> image shows specifics to match, point me at it.
