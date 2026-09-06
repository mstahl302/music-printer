# Feature Spec — Resizable Preview Dialog

**Status:** IMPLEMENTED — built 2026-09-06.
**Date:** 2026-09-06

---

## 1. Summary

Let the user drag-resize the **Preview** dialog so more than ~1.5
thumbnail blocks are visible at once. Main-window resizing was considered
and dropped — not wanted.

## 2. Design

The thumbnail canvas already lives in a `grid(sticky="nsew")` cell; it
just had no permission or weight to grow, and its inner frame (`body`)
didn't follow the canvas's width the way `FileList`'s canvas already does.

1. `self.resizable(True, True)` (was `False, False`), `self.minsize(420, 320)`.
2. Grid weight down the chain: the dialog's own `rowconfigure`/
   `columnconfigure(weight=1)`, and on `frm`, row 1 (the canvas row) and
   column 0.
3. `body.columnconfigure(0, weight=1)` and a `canvas.bind("<Configure>", …
   itemconfigure(winid, width=e.width))` — the same width-follow pattern
   `FileList` already uses — so growing the dialog widens the blocks
   instead of leaving a fixed-width column with dead space beside it.

No change to block layout, thumbnails, the strip control
([spec_preview_strip_control.md](spec_preview_strip_control.md)), or any
other dialog (`RunDialog` stays fixed-size; the main window was explicitly
left alone).

## 3. Out of scope

- The main window (considered, dropped by request).
- Persisting dialog size across launches.
- A minimum/maximum thumbnail size or a multi-column thumbnail grid —
  growing the dialog just reveals more of the existing single-column,
  vertically-scrolling list.

## 4. Tests

`tests/test_preview.py::test_preview_dialog_is_resizable_and_shows_more_when_grown`:
builds an 8-file preview, asserts `resizable()` is now `(1, 1)`, grows the
window via `geometry(...)`, and checks (a) the canvas's visible-fraction
of the block list (`yview()` span) grows, and (b) the inner frame's
configured width tracks the canvas's actual width.
