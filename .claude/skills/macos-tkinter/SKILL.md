---
name: macos-tkinter
description: >-
  Gotchas and working patterns for building or modifying a Tkinter GUI on macOS
  (aqua, Tk 9). Use when touching main.py / musicprinter/widgets.py / any
  tk.Toplevel dialog: colored buttons, Canvas wheel+trackpad scrolling, Cmd-Q
  shutdown, ttk.Progressbar cleanup, worker threads, and headless GUI tests.
---

# macOS Tkinter (aqua, Tk 9)

This project runs on the python.org universal2 build → **Tk 9.0.4, aqua**.
(The system Python's Tk 8.5 is unusable; always use the venv.) The aqua theme
and Tk 9's event model break several things that "just work" on Linux/Windows.
Every item below cost real debugging — reach for the named implementation
rather than re-deriving.

## Checklist when adding UI

- [ ] Button that needs a fill colour → `widgets.button(...)`, never `tk.Button`/`ttk.Button`.
- [ ] New scroll region (Canvas + inner frame) → call `bind_region_scroll(canvas)` once in `__init__`.
- [ ] New `tk.Toplevel` with timers → give it `close()` that cancels its `after()` ids / stops its progressbar; have `App._on_close` call it.
- [ ] New recurring `after()` in `App` → schedule via `self._after(...)` so shutdown can cancel it.
- [ ] Work that blocks → run in a thread, but read Tk vars first on the main thread and return results through `self._q` (never touch widgets off-thread).
- [ ] New behaviour → headless test in `tests/`, driven with `event_generate` + `_pump`.

## 1. Coloured buttons — `musicprinter/widgets.py`

`tk.Button` and `ttk.Button` **ignore `background` while enabled** on aqua (you
get flat grey when active, a tinted `highlightbackground` when the window is
unfocused, never the colour you asked for). Solution: `widgets.Button` is a
`tk.Label` subclass with manual `<Enter>/<Leave>/<Button-1>/<ButtonRelease-1>`
bindings for hover/press/click and a `set_enabled(bool)` method.

- `highlightthickness=0` — the stray grey border is the focus ring.
- **Never override `configure()`** on the subclass. tkinter internally calls
  `configure({...})` positionally; an override without a positional `cnf`
  param raises `TypeError` from deep inside Tk and freezes the event loop.
- `_release` re-checks the pointer is still inside before firing the command.

## 2. Canvas scroll regions — `bind_region_scroll` in `main.py`

Also see memory `tk9-macos-scroll`. A `tk.Canvas` gets **no default bindings**
for any scroll input on Tk 9 aqua (Listbox/Text/Scrollbar do — that's why
scrolling only worked over the scrollbar).

- **Three unrelated events:** `<MouseWheel>` (physical wheel),
  `<TouchpadScroll>` (two-finger trackpad, packed precise deltas in `%D`),
  and plain key events. `<Button-4>/<Button-5>` never fire on aqua.
- **Bind on `canvas.winfo_toplevel()`**, not per-widget (wheel events don't
  bubble to the masked canvas) and not `bind_all` gated on `<Enter>/<Leave>`
  (those never fire — the inner frame covers the canvas). The toplevel path is
  in every descendant's bindtags, so one handler covers the subtree and dies
  with the window.
- **Dispatch by `event.widget` ancestry** (walk `.master` to the canvas), not
  pointer coordinates — then re-rendering the rows can't break it. Keep a
  pointer-rect fallback for key events.
- `<TouchpadScroll>`: detect with `str(e.type) == "39"` (no `tk.EventType`
  member in 3.14). Unpack `%D` like `tk::PreciseScrollDeltas`:
  `dx = d>>16; low = d & 0xffff; dy = low if low < 0x8000 else low-0x10000`.
  Accumulate `dy` and step `yview_scroll(-steps, "units")` or it's a blur.
  Positive `dy` = toward top (matches macOS natural scrolling and Tk's Listbox
  binding).
- `<MouseWheel>`: aqua factor is **-40 per notch**, i.e.
  `yview_scroll(int(-e.delta/40) or ±1, "units")` — do **not** clamp small
  deltas to zero.

## 3. Cmd-Q / app-menu Quit — `App._on_close` in `main.py`

macOS "Quit" and ⌘Q **bypass `WM_DELETE_WINDOW`**. Without handling, the
interpreter tears down while `after()` callbacks are still queued →
"«App» quit unexpectedly".

- `self.createcommand("tk::mac::Quit", self._on_close)` in `__init__` (wrap in
  `try/except tk.TclError` for non-mac).
- `_on_close` is **idempotent** (`self._closing` flag, set first).
- Cancel every tracked recurring `after()` id; `_pump`/`_poll_job` also bail
  when `self._closing`.
- Call each child `tk.Toplevel`'s `close()` (stops its timers/progressbar),
  then `shutil.rmtree` temp, then `self.quit()` **then** `self.destroy()`.

## 4. `ttk.Progressbar`

`.start(ms)` schedules an internal `ttk::progressbar::Autoincrement` `after`
loop. If the interpreter is destroyed with it still running you get
`cannot invoke "winfo" command: application has been destroyed`. Call
`self._bar.stop()` in the dialog's `close()` before `destroy()`.

## 5. Worker threads

Reading a Tk variable (`StringVar.get()`) or touching a widget from a
background thread **silently freezes or crashes** the app. Pattern in
`App._begin_pass` / `_submit_worker`: read every Tk value on the main thread,
pass them as plain args to the worker, and push results back onto
`self._q` (a `queue.Queue`) which `_pump` drains from an `after(80, ...)` loop.

## 6. Headless GUI tests — `tests/conftest.py`, `tests/test_scroll.py`

- Autouse fixture per test: `tkinter._default_root = None` + `gc.collect()`
  after each test (many `tk.Tk()` per process is otherwise flaky).
- Env knobs so tests run fast and silent: `MUSIC_PRINTER_POLL_MS=40`,
  `MUSIC_PRINTER_NO_SOUND=1` (skips the `afplay` subprocess).
- `event_generate` quirks: screen coords are `rootx=`/`rooty=` (the event
  arrives as `e.x_root`/`e.y_root`); wheel delta is `delta=`; a synthetic
  `serial` does not reliably increment, so don't build throttles on `%#` in
  tests.
- Drive the state machine with a `FakePrinting` mock past `build_pass_pdf`
  and a `_pump(app, until)` helper. **Never let a headless run reach the real
  `printing` module** — it submits real CUPS jobs.

## 7. Packaging

`.app` via `build.sh` → `pyinstaller --windowed --icon assets/icon.icns`.
`run.sh` for a plain `python main.py` from the venv.
