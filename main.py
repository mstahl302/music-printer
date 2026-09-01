#!/usr/bin/env python3
"""Music Printer — Tkinter front-end and two-pass state machine.

The main window holds an ordered list of one or more PDFs. Add files, drag
them into performance order, hit Preview. The preview dialog's Start hands
off to the run dialog, which prints the whole set as one two-pass job with
one flip. See docs/specification.md, docs/spec_guided_print_dialog.md and
docs/spec_batch_printing.md.
"""

from __future__ import annotations

import base64
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from musicprinter import jobs, printing, rundialog, settings, widgets
from musicprinter.pdfio import PdfError, render_thumbnail_png

# UI label  ->  strip mode
COVER_MODES = {
    "Always Remove First Page": "always",
    "Don't Remove": "none",
    "Smart Strip (remove if detected)": "smart",
}
MODE_TO_LABEL = {v: k for k, v in COVER_MODES.items()}
DEFAULT_COVER_LABEL = "Smart Strip (remove if detected)"

FLIP_SOUND = "/System/Library/Sounds/Ping.aiff"
_POLL_MS = max(20, int(os.environ.get("MUSIC_PRINTER_POLL_MS", "700")))

# state machine
READY = "ready"
PRINTING_PASS1 = "printing_pass1"
WAIT_FOR_FLIP = "wait_for_flip"
PRINTING_PASS2 = "printing_pass2"
PRINTING_SINGLE = "printing_single"
DONE = "done"
DONE_ERROR = "done_error"

_PRINTING = {PRINTING_PASS1, PRINTING_PASS2, PRINTING_SINGLE}
_PASS_HEADING = {"even": "Printing — pass 1 of 2", "odd": "Printing — pass 2 of 2",
                 "single": "Printing"}
_PASS_SIDE = {"even": "Even pages", "odd": "Odd pages", "single": "Pages"}

_PINK_BG, _PINK_FG = "#f2c7d6", "#8a2c4c"


# ============================================================ file list
_WHEEL_SEQS = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def _wheel_scroll(canvas, e) -> str:
    """Scroll ``canvas`` for one wheel/trackpad event, only when it overflows.

    Bound directly on the scrollable widgets (a `bind_all` on <Enter>/<Leave>
    never fires on macOS because the inner frame covers the canvas)."""
    bb = canvas.bbox("all")
    if not bb or bb[3] - bb[1] <= canvas.winfo_height():
        return "break"
    num = getattr(e, "num", 0)
    if num == 4:
        canvas.yview_scroll(-2, "units")
    elif num == 5:
        canvas.yview_scroll(2, "units")
    else:
        step = int(-1 * e.delta)
        step = max(-4, min(4, step)) or (-1 if e.delta >= 0 else 1)
        canvas.yview_scroll(step, "units")
    return "break"


def _bind_scroll_tree(widget, canvas, *, focus_target=None) -> None:
    """Bind wheel scrolling on ``widget`` and every current descendant."""
    handler = lambda e: _wheel_scroll(canvas, e)
    stack = [widget]
    while stack:
        w = stack.pop()
        for seq in _WHEEL_SEQS:
            w.bind(seq, handler, add="+")
        if focus_target is not None:
            w.bind("<Button-1>", lambda _e: focus_target.focus_set(), add="+")
        stack.extend(w.winfo_children())


def _elide(name: str, maxlen: int) -> str:
    """Middle-truncate a filename, keeping the extension."""
    if len(name) <= maxlen:
        return name
    stem, dot, ext = name.rpartition(".")
    if dot and 0 < len(ext) <= 5:
        keep = maxlen - len(ext) - 2
        return f"{stem[:max(1, keep)]}….{ext}"
    return name[:maxlen - 1] + "…"


class FileList(ttk.Frame):
    """Bordered, striped, scrollable list of file rows: drag handle,
    (elided) filename, page count / warning, red remove button. Shows
    empty placeholder rows so it reads as a list before anything is added."""

    VISIBLE = 6
    ROW_PX = 32
    WIDTH = 460
    NAME_MAX = 40
    STRIPE = ("#ffffff", "#f1f1f4")
    HINT = "  Add PDFs to build your set…"

    def __init__(self, parent, *, on_change) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self.files: list[Path] = []
        self._entry_by_path: dict[str, jobs.FileEntry] = {}
        self._drag_from: int | None = None
        self._drop_target: int | None = None

        wrap = tk.Frame(self, bd=1, relief="solid", bg=self.STRIPE[0])
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(wrap, highlightthickness=0, bd=0, bg=self.STRIPE[0],
                                 width=self.WIDTH, height=self.ROW_PX * self.VISIBLE)
        self._sb = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=self.STRIPE[0])
        self._winid = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._on_scroll)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._inner.bind("<Configure>",
                         lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfigure(self._winid, width=e.width))
        self._inner.columnconfigure(0, weight=1)

        self._drop_line = tk.Frame(self._inner, height=2, bg="#1a1a1a")  # drag indicator

        self._canvas.configure(takefocus=True)
        for w in (self._canvas, self._inner):
            for seq in _WHEEL_SEQS:
                w.bind(seq, lambda e: _wheel_scroll(self._canvas, e), add="+")
        for seq in ("<Up>", "<Down>", "<Prior>", "<Next>"):
            self._canvas.bind(seq, self._arrow, add="+")
        self._canvas.bind("<Button-1>", lambda _e: self._canvas.focus_set(), add="+")
        self._render()

    # ---- keyboard scrolling (wheel is bound per-row in _render) ----
    def _arrow(self, e):
        bb = self._canvas.bbox("all")
        if not bb or bb[3] - bb[1] <= self._canvas.winfo_height():
            return
        move = {"Up": (-1, "units"), "Down": (1, "units"),
                "Prior": (-1, "pages"), "Next": (1, "pages")}.get(e.keysym)
        if move:
            self._canvas.yview_scroll(*move)
            return "break"

    def _on_scroll(self, lo, hi) -> None:
        full = float(lo) <= 0.0 and float(hi) >= 1.0
        if full:
            self._sb.grid_remove()
        else:
            self._sb.grid(row=0, column=1, sticky="ns")
        self._sb.set(lo, hi)

    def set_files(self, files) -> None:
        self.files = list(files)
        self._render()

    def add(self, paths) -> None:
        self.files.extend(Path(p) for p in paths)
        self._render()
        self._on_change()

    def set_entries(self, entries) -> None:
        self._entry_by_path = {str(e.path): e for e in entries}
        self._render()

    # ---- rendering ---------------------------------------------
    def _render(self) -> None:
        for w in self._inner.winfo_children():
            if w is not self._drop_line:
                w.destroy()
        self._drop_line.place_forget()
        n_rows = max(len(self.files), self.VISIBLE)
        for i in range(n_rows):
            stripe = self.STRIPE[i % 2]
            row = tk.Frame(self._inner, bg=stripe, height=self.ROW_PX)
            row.grid(row=i, column=0, sticky="ew")
            row.grid_propagate(False)
            row.columnconfigure(1, weight=1)
            if i < len(self.files):
                self._fill_row(row, i, stripe)
            elif i == 0:
                tk.Label(row, text=self.HINT, bg=stripe, fg="#9a9a9a", anchor="w").grid(
                    row=0, column=0, columnspan=4, sticky="w")
            _bind_scroll_tree(row, self._canvas, focus_target=self._canvas)

    def _fill_row(self, row, i: int, stripe: str) -> None:
        path = self.files[i]
        row._path = path  # type: ignore[attr-defined]

        grip = tk.Label(row, text="⠿", bg=stripe, fg="#9a9a9a", cursor="fleur")
        grip.grid(row=0, column=0, padx=(7, 8))
        grip.bind("<ButtonPress-1>", lambda _e, idx=i: self._drag_start(idx))
        grip.bind("<B1-Motion>", self._drag_motion)
        grip.bind("<ButtonRelease-1>", self._drag_drop)

        tk.Label(row, text=_elide(path.name, self.NAME_MAX), bg=stripe, anchor="w").grid(
            row=0, column=1, sticky="ew")

        e = self._entry_by_path.get(str(path))
        if e is None:
            txt, fg = "…", "#888"
        elif e.error:
            txt, fg = f"⚠ {e.error}", "#b23"
        else:
            txt, fg = f"{e.n_effective} pages", "#888"
        tk.Label(row, text=txt, bg=stripe, fg=fg).grid(row=0, column=2, padx=8)

        rm = widgets.button(row, "×", widgets.RED, lambda p=path: self._remove(p))
        rm.configure(padx=6, pady=0, font=("TkDefaultFont", 11))
        rm.grid(row=0, column=3, padx=(0, 7))

    def _remove(self, path: Path) -> None:
        self.files = [p for p in self.files if p != path]
        self._render()
        self._on_change()

    # ---- drag to reorder -------------------------------------
    def _real_rows(self):
        return [r for r in self._inner.winfo_children() if getattr(r, "_path", None) is not None]

    def _drag_start(self, idx: int) -> None:
        self._drag_from = idx
        self._drop_target = idx

    def _drag_motion(self, event) -> None:
        if self._drag_from is None:
            return
        rows = self._real_rows()
        if not rows:
            return
        y = event.y_root - self._inner.winfo_rooty()
        target = len(rows)
        for idx, r in enumerate(rows):
            if y < r.winfo_y() + r.winfo_height() / 2:
                target = idx
                break
        self._drop_target = target
        if target < len(rows):
            line_y = rows[target].winfo_y()
        else:
            line_y = rows[-1].winfo_y() + rows[-1].winfo_height()
        self._drop_line.place(x=0, y=max(0, line_y - 1), relwidth=1)
        self._drop_line.lift()

        vy = event.y_root - self._canvas.winfo_rooty()
        if vy < 18:
            self._canvas.yview_scroll(-1, "units")
        elif vy > self._canvas.winfo_height() - 18:
            self._canvas.yview_scroll(1, "units")

    def _drag_drop(self, _event) -> None:
        src, dst = self._drag_from, self._drop_target
        self._drag_from = self._drop_target = None
        self._drop_line.place_forget()
        if src is None or dst is None:
            return
        if dst > src:
            dst -= 1
        dst = max(0, min(dst, len(self.files) - 1))
        if dst != src:
            p = self.files.pop(src)
            self.files.insert(dst, p)
            self._render()
            self._on_change()

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for row in self._inner.winfo_children():
            for child in row.winfo_children():
                try:
                    child.configure(state=state)
                except tk.TclError:
                    pass


# ========================================================= preview dialog
class PreviewDialog(tk.Toplevel):
    def __init__(self, parent, *, setplan: jobs.SetPlan, on_start) -> None:
        super().__init__(parent)
        self.title("Preview")
        self.resizable(False, False)
        self.transient(parent)
        self._setplan = setplan
        self._on_start = on_start
        self._thumbs: list[tk.PhotoImage] = []
        self._thumb_labels: list[ttk.Label] = []
        self._q: queue.Queue = queue.Queue()
        self._closing = False
        self._afters: list[str] = []

        frm = ttk.Frame(self, padding=16)
        frm.grid(sticky="nsew")

        canvas = tk.Canvas(frm, highlightthickness=0, width=460,
                           height=min(430, 96 * max(1, setplan.n_files) + 8))
        sb = ttk.Scrollbar(frm, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        try:
            canvas.configure(bg=ttk.Style().lookup("TFrame", "background") or None)
        except tk.TclError:
            pass
        for seq in _WHEEL_SEQS:
            canvas.bind(seq, lambda e: _wheel_scroll(canvas, e), add="+")
            body.bind(seq, lambda e: _wheel_scroll(canvas, e), add="+")

        layout = setplan.layout
        for i, e in enumerate(setplan.ok_entries):
            block = ttk.Frame(body, padding=(0, 8))
            block.grid(row=i, column=0, sticky="ew")
            thumb = ttk.Label(block, text="…", width=10, anchor="center",
                              relief="solid", borderwidth=1)
            thumb.grid(row=0, column=0, rowspan=2, padx=(0, 12))
            self._thumb_labels.append(thumb)
            ttk.Label(block, text=e.path.name, font=("TkDefaultFont", 12, "bold")).grid(
                row=0, column=1, sticky="w")
            line = ttk.Frame(block)
            line.grid(row=1, column=1, sticky="w", pady=(2, 0))
            col = 0
            if e.cover_removed:
                chip = tk.Label(line, text=" cover removed ", bg=_PINK_BG, fg=_PINK_FG,
                                font=("TkDefaultFont", 9))
                chip.grid(row=0, column=col, padx=(0, 6))
                col += 1
            sheets = layout.file_sheets(i) if layout else 0
            ttk.Label(line, text=f"{e.n_effective} pages · {sheets} sheets",
                      foreground="#777").grid(row=0, column=col)

        _bind_scroll_tree(body, canvas)

        bar = ttk.Frame(frm, padding=(0, 14, 0, 0))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(0, weight=1)
        n = setplan.sheets_to_prepare
        msg = ttk.Frame(bar)
        msg.grid(row=0, column=0, sticky="w")
        ttk.Label(msg, text=f"Printing requires {n} sheet{'s' if n != 1 else ''} of paper",
                  font=("TkDefaultFont", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(msg, text="When you're ready, click Start.",
                  foreground="#666").grid(row=1, column=0, sticky="w")
        widgets.button(bar, "Start", widgets.BLUE, self._start, big=True).grid(row=0, column=1)

        self._center_on(parent)
        self._afters.append(self.after(0, self._grab))
        self._afters.append(self.after(60, self._pump))
        threading.Thread(target=self._render_thumbs,
                         args=([e.path for e in setplan.ok_entries],
                               [e.cover_removed for e in setplan.ok_entries]),
                         daemon=True).start()

    def _render_thumbs(self, paths, offsets) -> None:
        for i, (p, off) in enumerate(zip(paths, offsets)):
            try:
                png = render_thumbnail_png(p, off, max_px=132)
            except Exception:
                png = None
            self._q.put((i, png))

    def _pump(self) -> None:
        try:
            while True:
                i, png = self._q.get_nowait()
                if png and i < len(self._thumb_labels):
                    try:
                        img = tk.PhotoImage(data=base64.b64encode(png).decode(), format="png")
                        self._thumbs.append(img)
                        self._thumb_labels[i].configure(image=img, text="")
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        if self._closing:
            return
        try:
            if self.winfo_exists():
                self._afters.append(self.after(80, self._pump))
        except tk.TclError:
            pass

    def _start(self) -> None:
        plan = self._setplan
        self.close()
        self._on_start(plan)

    def close(self) -> None:
        self._closing = True
        for tid in self._afters:
            try:
                self.after_cancel(tid)
            except tk.TclError:
                pass
        self._afters.clear()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _grab(self) -> None:
        if self._closing:
            return
        try:
            self.grab_set()
        except tk.TclError:
            self._afters.append(self.after(80, self._grab_once))

    def _grab_once(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _center_on(self, parent) -> None:
        try:
            self.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 3)}")
        except tk.TclError:
            pass


# ================================================================ app
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Music Printer")
        self.resizable(False, False)
        self._closing = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # macOS app-menu Quit / Cmd-Q — route through the clean shutdown so the
        # interpreter doesn't tear down mid-callback ("quit unexpectedly").
        try:
            self.createcommand("tk::mac::Quit", self._on_close)
        except tk.TclError:
            pass

        self.cfg = settings.load()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="music-printer-"))
        self._q: queue.Queue = queue.Queue()

        self.printer = tk.StringVar(value=self.cfg["last_printer"])
        self.printer_display = tk.StringVar(value="")
        self._printers: dict[str, printing.Printer] = {}
        self.cover_label = tk.StringVar(
            value=MODE_TO_LABEL.get(self.cfg["strip_mode"], DEFAULT_COVER_LABEL))

        self.setplan: jobs.SetPlan | None = None
        self._plan_token = 0

        self.state = READY
        self.dialog: rundialog.RunDialog | None = None
        self._job_id: str | None = None
        self._gone_polls = 0
        self._canceling = False
        self._pass = ""
        self._afters: set[str] = set()

        self.printer_warn = tk.StringVar(value="")
        self.status = tk.StringVar(value="Add one or more PDFs.")

        self._build()
        self._load_printers()
        self._after(80, self._pump)

    def _after(self, ms: int, fn) -> str:
        """Schedule a callback whose id is tracked so _on_close can cancel it."""
        holder: list[str] = []

        def run() -> None:
            if holder:
                self._afters.discard(holder[0])
            if not self._closing:
                fn()

        tid = self.after(ms, run)
        holder.append(tid)
        self._afters.add(tid)
        return tid

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        pad = {"padx": 10, "pady": 5}
        frm = ttk.Frame(self, padding=12)
        frm.grid()
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Printer:").grid(row=0, column=0, sticky="w", **pad)
        self.printer_menu = ttk.OptionMenu(frm, self.printer_display, "")
        self.printer_menu.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Label(frm, textvariable=self.printer_warn, foreground="#b00").grid(
            row=1, column=1, columnspan=2, sticky="w", padx=10)

        ttk.Label(frm, text="Strip Cover Sheet:").grid(row=2, column=0, sticky="w", **pad)
        self.cover_menu = ttk.OptionMenu(
            frm, self.cover_label, self.cover_label.get(), *COVER_MODES,
            command=lambda _=None: self._recompute())
        self.cover_menu.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)

        self.filelist = FileList(frm, on_change=self._recompute)
        self.filelist.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)

        row = ttk.Frame(frm)
        row.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        row.columnconfigure(0, weight=1)
        self.add_btn = widgets.button(row, "Add PDFs…", widgets.BLUE, self._pick_files)
        self.add_btn.grid(row=0, column=0, sticky="w")
        self.preview_btn = widgets.button(row, "Preview", widgets.BLUE, self._open_preview, big=True)
        self.preview_btn.grid(row=0, column=1, sticky="e")

        ttk.Label(frm, textvariable=self.status, foreground="#555").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 0))

        self._set_state(READY)

    # ---------------------------------------------------------- printers
    def _load_printers(self) -> None:
        try:
            printers = printing.list_printers()
        except Exception as exc:
            self.status.set(f"Could not list printers: {exc}")
            return
        self._printers = {p.name: p for p in printers}
        menu = self.printer_menu["menu"]
        menu.delete(0, "end")
        for p in printers:
            label = f"{p.label}  (default)" if p.is_default else p.label
            menu.add_command(label=label, command=lambda n=p.name: self._choose_printer(n))
        names = [p.name for p in printers]
        if self.printer.get() not in names:
            self.printer.set(next((p.name for p in printers if p.is_default),
                                  names[0] if names else ""))
        self._sync_printer_display()
        self._check_printer()

    def _choose_printer(self, name: str) -> None:
        self.printer.set(name)
        self._sync_printer_display()
        self.cfg["last_printer"] = name
        settings.save(self.cfg)
        self._check_printer()

    def _sync_printer_display(self) -> None:
        p = self._printers.get(self.printer.get())
        self.printer_display.set(
            self.printer.get() if p is None
            else (f"{p.label}  (default)" if p.is_default else p.label))

    def _check_printer(self) -> None:
        name = self.printer.get()
        self.printer_warn.set(
            "This printer is paused — jobs will queue but not print."
            if name and printing.printer_state(name) == "disabled" else "")

    # ------------------------------------------------------ files + plan
    def _pick_files(self) -> None:
        start = self.cfg["last_folder"] or str(Path.home())
        paths = filedialog.askopenfilenames(
            title="Add sheet music (PDF)", initialdir=start,
            filetypes=[("PDF files", "*.pdf")])
        if not paths:
            return
        self.cfg["last_folder"] = str(Path(paths[0]).parent)
        settings.save(self.cfg)
        self.filelist.add(paths)

    def _recompute(self) -> None:
        self.cfg["strip_mode"] = COVER_MODES[self.cover_label.get()]
        settings.save(self.cfg)
        if self.state != READY:
            return
        self.setplan = None
        self._plan_token += 1
        token = self._plan_token
        files = list(self.filelist.files)
        if not files:
            self.status.set("Add one or more PDFs.")
            self._set_state(READY)
            return
        self.status.set("Reading…")
        threading.Thread(
            target=self._plan_worker,
            args=(token, files, self.cfg["strip_mode"],
                  float(self.cfg["confidence_threshold"])),
            daemon=True).start()

    def _plan_worker(self, token: int, files, mode: str, threshold: float) -> None:
        try:
            setplan = jobs.build_plan(files, mode, threshold=threshold)
            self._q.put(("plan", token, setplan))
        except Exception as exc:
            self._q.put(("plan_err", token, str(exc)))

    def _apply_plan(self, setplan: jobs.SetPlan) -> None:
        self.setplan = setplan
        self.filelist.set_entries(setplan.entries)
        bad = sum(1 for e in setplan.entries if not e.ok)
        if bad:
            self.status.set(f"{bad} file{'s' if bad != 1 else ''} can't be opened — "
                            "remove them to preview.")
        elif setplan.layout:
            self.status.set(f"{setplan.n_files} file{'s' if setplan.n_files != 1 else ''} · "
                            f"{setplan.sheets_to_prepare} sheets of paper")
        self._set_state(READY)

    # ================================================================ run
    def _open_preview(self) -> None:
        if not self._preview_ok():
            return
        PreviewDialog(self, setplan=self.setplan, on_start=self._start_run)

    def _preview_ok(self) -> bool:
        return (self.state == READY and self.setplan is not None
                and self.setplan.n_files >= 1 and not self.setplan.has_errors
                and self.setplan.layout is not None)

    def _start_run(self, setplan: jobs.SetPlan) -> None:
        self.setplan = setplan
        self._check_printer()
        if self.printer_warn.get() and not messagebox.askyesno(
                "Printer paused", f"{self.printer_warn.get()}\n\nQueue the job anyway?"):
            return
        self.dialog = rundialog.RunDialog(
            self, run_title=setplan.run_title,
            on_cancel=self._cancel, on_continue=self._start_pass2,
            on_close=self._close_dialog)
        self.dialog.show_phase(rundialog.PREPARING, detail="Building pass 1…")
        if setplan.single_pass:
            self._begin_pass("single", PRINTING_SINGLE)
        else:
            self._begin_pass("even", PRINTING_PASS1)

    def _start_pass2(self) -> None:
        self._begin_pass("odd", PRINTING_PASS2)

    def _begin_pass(self, which: str, state: str) -> None:
        self._canceling = False
        self._job_id = None
        self._gone_polls = 0
        self._pass = which
        self._set_state(state)
        if self.dialog:
            self.dialog.show_phase(rundialog.PRINTING, heading=_PASS_HEADING[which],
                                   detail="Sending…")
        threading.Thread(target=self._submit_worker,
                         args=(which, self.setplan, self.printer.get()),
                         daemon=True).start()

    def _submit_worker(self, which: str, setplan: jobs.SetPlan, printer_name: str) -> None:
        try:
            pdf = jobs.build_pass_pdf(setplan, which, self._tmpdir)
            reverse = bool(self.cfg.get("reverse_page_order", True))
            job_id = printing.submit(pdf, printer_name,
                                     title=f"{setplan.run_title} · {which}",
                                     reverse_order=reverse)
            settings.log(f"submit {which} job={job_id} file={pdf.name} "
                         f"files={setplan.n_files} sheets={setplan.sheets_to_prepare} "
                         f"mode={setplan.strip_mode} reverse={reverse}")
            self._q.put(("submitted", which, job_id))
        except Exception as exc:
            self._q.put(("submit_err", which, exc))

    def _detail(self, word: str) -> None:
        if self.dialog:
            self.dialog.set_detail(
                f"{_PASS_SIDE.get(self._pass, 'Pages')} · {word} · job {self._job_id}")

    def _poll_job(self) -> None:
        if self._closing or self.state not in _PRINTING or not self._job_id:
            return
        try:
            st = printing.job_status(self._job_id)
        except Exception as exc:
            self._finish_pass_failed(f"Lost track of the job: {exc}")
            return
        delay = _POLL_MS // 2 if self._canceling else _POLL_MS
        if st == "processing":
            self._detail("printing")
            self._after(delay, self._poll_job)
        elif st == "queued":
            self._detail("in the printer queue")
            self._after(delay, self._poll_job)
        elif st == "canceled" or (self._canceling and st in ("completed", "gone")):
            self._finish_pass_canceled()
        elif st == "aborted":
            self._finish_pass_failed(f"The printer aborted job {self._job_id}.")
        elif st == "completed":
            self._finish_pass_ok()
        else:  # gone
            self._gone_polls += 1
            (self._finish_pass_ok if self._gone_polls >= 3
             else lambda: self._after(delay, self._poll_job))()

    def _finish_pass_ok(self) -> None:
        settings.log(f"pass ok state={self.state} job={self._job_id}")
        self._job_id = None
        if self.state == PRINTING_PASS1:
            self._set_state(WAIT_FOR_FLIP)
            if self.dialog:
                self.dialog.show_phase(rundialog.FLIP)
                self.dialog.bring_forward()
            self._play_flip_cue()
        else:
            self._set_state(DONE)
            if self.dialog:
                self.dialog.show_phase(rundialog.DONE, detail="Double-sided copy printed.")

    def _finish_pass_canceled(self) -> None:
        settings.log(f"pass canceled state={self.state}")
        was_pass2 = self.state == PRINTING_PASS2
        self._job_id = None
        self._set_state(DONE_ERROR if was_pass2 else READY)
        if self.dialog:
            self.dialog.show_phase(
                rundialog.CANCELLED,
                detail=("Some sheets are printed on one side only, and there may be "
                        "back-printed sheets still in the printer's feed tray — pull "
                        "those out before the next job.") if was_pass2 else "")

    def _finish_pass_failed(self, message: str) -> None:
        settings.log(f"pass failed state={self.state}: {message}")
        self._job_id = None
        was_pass2 = self.state == PRINTING_PASS2
        self._set_state(DONE_ERROR if was_pass2 else READY)
        if self.dialog:
            self.dialog.show_phase(rundialog.FAILED, detail=message)
        else:
            messagebox.showerror("Printing", message)

    def _cancel(self) -> None:
        if self.state == WAIT_FOR_FLIP:
            if messagebox.askyesno(
                    "Stop here?",
                    "Pass 1 sheets are already printed. Discard this and start over?"):
                self._set_state(READY)
                if self.dialog:
                    self.dialog.show_phase(rundialog.CANCELLED, detail="")
            return
        if self.state in _PRINTING and self._job_id:
            self._canceling = True
            if self.dialog:
                self.dialog.disable_cancel()
                self.dialog.set_detail(f"Cancelling job {self._job_id}…")
            threading.Thread(target=self._cancel_worker, args=(self._job_id,),
                             daemon=True).start()

    def _cancel_worker(self, job_id: str) -> None:
        try:
            printing.cancel(job_id)
            self._q.put(("cancel_ok", job_id))
        except Exception as exc:
            self._q.put(("cancel_err", exc))

    def _close_dialog(self) -> None:
        if self.dialog:
            self.dialog.close()
            self.dialog = None
        self._set_state(READY)
        self._recompute()

    def _play_flip_cue(self) -> None:
        if os.environ.get("MUSIC_PRINTER_NO_SOUND"):
            return
        try:
            subprocess.Popen(["afplay", FLIP_SOUND],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                self.bell()
            except tk.TclError:
                pass

    # =========================================================== plumbing
    def _pump(self) -> None:
        if self._closing:
            return
        try:
            while True:
                kind, *rest = self._q.get_nowait()
                self._dispatch(kind, rest)
        except queue.Empty:
            pass
        try:
            self._after(80, self._pump)
        except tk.TclError:
            pass

    def _dispatch(self, kind: str, rest: list) -> None:
        if kind == "plan":
            token, setplan = rest
            if token == self._plan_token and self.state == READY:
                self._apply_plan(setplan)
        elif kind == "plan_err":
            token, msg = rest
            if token == self._plan_token and self.state == READY:
                self.setplan = None
                self.status.set(msg)
                self._set_state(READY)
        elif kind == "submitted":
            _which, job_id = rest
            self._job_id = job_id
            self._gone_polls = 0
            self._detail("queued")
            self._after(_POLL_MS, self._poll_job)
        elif kind == "submit_err":
            which, exc = rest
            self._finish_pass_failed(f"Could not send the {which} pass: {exc}")
        elif kind == "cancel_err":
            (exc,) = rest
            self._canceling = False
            if self.dialog:
                self.dialog.enable_cancel()
                self.dialog.set_detail(f"Couldn't cancel — {exc}. Try again.")
        # "cancel_ok" — _poll_job sees the terminal state

    def _set_state(self, state: str) -> None:
        self.state = state
        inputs = "normal" if state == READY else "disabled"
        self.printer_menu.config(state=inputs)
        self.cover_menu.config(state=inputs)
        self.add_btn.set_enabled(state == READY)
        self.filelist.set_enabled(state == READY)
        self.preview_btn.set_enabled(self._preview_ok())

    # ============================================================= close
    def _cleanup_tmp(self) -> None:
        for f in self._tmpdir.glob("music-printer-*.pdf"):
            try:
                f.unlink()
            except OSError:
                pass

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        for tid in list(self._afters):
            try:
                self.after_cancel(tid)
            except tk.TclError:
                pass
        self._afters.clear()
        if self._job_id and not self._canceling and self.state in _PRINTING:
            try:
                printing.cancel(self._job_id)
            except Exception:
                pass
        for w in list(self.winfo_children()):
            if isinstance(w, tk.Toplevel):
                closer = getattr(w, "close", None)   # RunDialog/PreviewDialog stop their timers
                try:
                    if callable(closer):
                        closer()
                    else:
                        w.grab_release()
                        w.destroy()
                except tk.TclError:
                    pass
        self.dialog = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        try:
            self.quit()       # leave the mainloop first
        finally:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
