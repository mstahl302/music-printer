# Cover-Sheet Detection Signals

**Status:** IMPLEMENTED — shipped in `musicprinter/covers/musicnotes.py` as
described below, based on a 12-file sample. The full-corpus validation in
§6 has not been run; treat the confidence numbers as good-but-unverified
at scale until it is.
**Date:** 2026-09-01
**Related:** [specification.md](specification.md) §7.1

This document defines how Music Printer decides whether page 1 of a source
PDF is a **vendor cover sheet** that should be removed before printing. The
specification references this doc; the heuristics are kept here so they can
be tuned without touching the spec.

---

## 1. What a Musicnotes cover sheet looks like

Every cover sheet in the sample follows one template:

```
From: "<SHOW / ALBUM>"
<SONG TITLE>
[from <SHOW>]                     (sometimes)
by
<COMPOSER NAME(S), ALL CAPS>
[Lyrics by: <NAME(S)>]            (sometimes)
Published Under License From
<PUBLISHER>
<one to four copyright / administration lines>
NOTICE: Purchasers of this musical file are entitled to use it for their
personal enjoyment and musical fulfillment.  However, any duplication,
adaptation, arranging and/or transmission of this copyrighted music
requires the written consent of the copyright owner(s) and of <PUBLISHER>.
Unauthorized uses are infringements of the copyright laws of the United
States and other countries and may subject the user to civil and/or
criminal penalties.
musicnotes.com

Authorized for use by <PURCHASER NAME>
```

Crucially, the cover page carries **no engraved music** — no staff lines,
effectively no vector drawing, ~700–900 characters of plain text, and one
small ornament image.

---

## 2. Sample corpus (2026-09-01)

12 files pulled from Google Drive `/Music/Vocal/Songs/*` and nearby
folders. All US Letter (612×792 pt). Hand-labelled:

| File | Pages | Page 1 | Producer / origin |
|---|---|---|---|
| Along the Way (Edges) | 11 | **cover** | PDFsharp / PDFCreator |
| Willkommen (Cabaret) | 10 | **cover** | PDFsharp / PDFCreator |
| Nobody Needs To Know (MN0107784) | 14 | **cover** | PDFsharp / PDFCreator |
| Quiet (MN0147974) | 8 | **cover** | PDFsharp / PDFCreator |
| Settle for Me (MN0159810) | 10 | **cover** | PDFsharp / PDFCreator |
| They Just Keep Moving the Line | 9 | **cover** | PDFsharp / PDFCreator |
| Best Part | 6 | music | PDFium (re-saved) |
| Corner of the Sky | 4 | music | Chrome / Skia (re-saved) |
| Fine (Ordinary Days) | 16 | music | Chrome / Skia — PDF title "Print Center \| Musicnotes" |
| Mambo Italiano | 4 | music | Chrome / Skia — PDF title "Print Center \| Musicnotes" |
| If the World Was Ending | 5 | music | PDFium (re-saved) |
| July | 6 | music | PDFium (re-saved) |

Every one is a Musicnotes purchase. The six "music on page 1" files were
re-saved through a browser at some point, which had already dropped the
cover. So the detector's job is **not** "is this Musicnotes" — it is
"is *page 1* a cover".

---

## 3. Signals, measured

Values are page-1 measurements via PyMuPDF (`page.get_drawings()`,
`page.get_text()`, `page.get_images()`).

### 3.1 Primary — structural: "no engraved music on page 1"  → **A**

| Metric | Cover pages (n=6) | Music page-1 (n=6) |
|---|---|---|
| staff lines (horizontal segments > 120 pt, Δy < 1.5 pt) | **0** | 30 – 55 |
| vector draw ops (`len(get_drawings())`) | **1** | 218 – 564 |

Perfect separation. Rule:

```
A = (staff_line_count(page1) == 0) and (vector_draw_count(page1) <= 2)
```

### 3.2 Primary — text: Musicnotes cover boilerplate  → **B**

Case-insensitive, whitespace-collapsed substring test on page-1 text.
Each phrase below was present on **6/6** covers and **0/6** music page-1s:

- `published under license from`
- `purchasers of this musical file are entitled to use it for their personal enjoyment and musical fulfillment`
- `unauthorized uses are infringements of the copyright laws of the united states`

```
B = any(phrase in norm(text(page1)) for phrase in MUSICNOTES_COVER_PHRASES)
```

### 3.3 Corroborators (not decisive, not gates)

- Page 1 has **exactly one** image, small (ornament). Music page-1s had 0.
- Page-1 text length 650–900 chars.
- Page 1 begins `From: "…"` then a line `by` then an ALL-CAPS name line.
- Producer `PDFsharp … / PDFCreator` correlated 6/6 with covers in this
  sample, `PDFium` / `Skia` 6/6 with no-cover. **Correlation only** — a
  cover-bearing file re-saved through Chrome would keep the cover and
  change the producer. Do not gate on it.

### 3.4 Anti-signals / guards

- **`musicnotes.com` appears on nearly every page of nearly every file.**
  Useless for cover detection. (This is the signal to *avoid*.)
- Song title and "Words and Music by …" also appear on the music page 1 of
  cover-less files — so a title/composer block match **alone** must not
  trigger a strip.
- If page 1 is dominated by a single full-page raster image (scanned
  music), `A` could be true with no real cover. Guard: require page-1
  extractable text length > 150 and no image covering > 50 % of the page
  before treating `A` alone as meaningful.

---

## 4. Decision — `smart` mode

Let `A` and `B` be as above. Confidence:

| Case | Confidence | Action at threshold 0.70 |
|---|---|---|
| `A ∧ B` | **0.97** | strip page 1 |
| `A ∧ ¬B`, text > 150 chars, no full-page image | **0.75** | strip page 1 |
| `B ∧ ¬A` | 0.35 | keep (structural check failed — suspicious) |
| neither | 0.0 | keep |

`confidence_threshold` is configurable (default **0.70**). The plan
preview always shows the outcome and the first page (post-strip)
thumbnail, so the user can veto before printing.

### Other modes

- **`none`** — never strip.
- **`always`** — strip page 1 unconditionally, unless the file has only
  one page (then do nothing and say so in the preview).

---

## 5. Extensibility

```
musicprinter/covers/
  __init__.py     # CoverDetector protocol, REGISTRY, detect_cover(path, mode, threshold)
  base.py         # shared helpers:
                  #   staff_line_count(page), vector_draw_count(page),
                  #   norm(text), page_has_full_page_image(page)
  musicnotes.py   # MusicnotesCoverDetector: MUSICNOTES_COVER_PHRASES + the A/B rule
```

A `CoverDetector` returns `CoverMatch(detector, pages=(0,), confidence,
reason)` or `None`. `detect_cover` runs every detector in `REGISTRY` and,
for `smart`, keeps the highest-confidence match ≥ threshold.

To add a vendor (e.g. **Sheet Music Direct**, **Hal Leonard Digital**,
**MuseScore.com** exports): add a module with that vendor's boilerplate
phrases, reuse the structural `A` gate from `base.py`, append the detector
to `REGISTRY`. No changes to page planning or printing.

---

## 6. Validation plan

1. Enumerate every PDF under Drive `/Music/Vocal/Songs/*`.
2. Hand-label cover / no-cover.
3. Tune `MUSICNOTES_COVER_PHRASES` and `confidence_threshold` for **zero
   false strips** (a wrongly removed first page of music is the
   unacceptable error) and maximum true strips.
4. Freeze a small labelled subset as `tests/fixtures/` with expected
   `CoverMatch` output.

Numbers in §3 are from a 12-file sample. This validation plan has **not**
been run yet — it's a good follow-up, not a blocker: `smart` mode ships
today on the 12-file numbers, and `none` / `always` remain available as an
escape hatch if a real file trips it up.
