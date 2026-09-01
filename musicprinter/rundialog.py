"""The modal run dialog — owns a print run from Start to a terminal state.

Presentation only: ``main.App`` drives it via :meth:`RunDialog.show_phase`;
the two-pass state machine is unchanged. See
docs/spec_guided_print_dialog.md.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

# phases
PREPARING = "preparing"
PRINTING = "printing"
FLIP = "flip"
DONE = "done"
CANCELLED = "cancelled"
FAILED = "failed"

_ACTIVE = {PREPARING, PRINTING, FLIP}
_TERMINAL = {DONE, CANCELLED, FAILED}

_HEADING = {
    PREPARING: "Preparing…",
    PRINTING: "Printing…",
    FLIP: "Flip the stack",
    DONE: "Done",
    CANCELLED: "Job cancelled",
    FAILED: "Couldn't finish",
}
_HEADING_FG = {FLIP: "#c27214", FAILED: "#c0453a", DONE: "#3a8a5c"}

# button colours (green = continue, red = cancel, blue = acknowledge)
_GREEN, _RED, _BLUE = "#2f8f4e", "#c0392b", "#2b5fb0"

# ms between indeterminate-bar steps — higher is calmer (Tk default is 50)
_BAR_MS = 55

FLIP_INSTRUCTION = (
    "Take the printed pages out, flip the whole stack over the SHORT edge, "
    "and put them back in the tray."
)


def _darken(hex_colour: str, factor: float = 0.82) -> str:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def _button(parent, text, colour, command):
    """A flat, filled button — ttk on macOS ignores background, tk.Button + flat relief does not."""
    return tk.Button(
        parent, text=text, command=command,
        bg=colour, fg="white", activebackground=_darken(colour), activeforeground="white",
        disabledforeground="#e6e6e6", highlightbackground=colour,
        relief="flat", borderwidth=0, highlightthickness=0,
        font=("TkDefaultFont", 12), padx=16, pady=7, cursor="pointinghand",
    )


def _recolour(btn, colour) -> None:
    btn.configure(bg=colour, activebackground=_darken(colour), highlightbackground=colour)


class RunDialog(tk.Toplevel):
    def __init__(self, parent, *, run_title: str,
                 on_cancel, on_continue, on_close) -> None:
        super().__init__(parent)
        self.title(run_title)
        self.resizable(False, False)
        self.transient(parent)

        self._on_cancel = on_cancel
        self._on_continue = on_continue
        self._on_close = on_close
        self._phase: str | None = None

        self.protocol("WM_DELETE_WINDOW", self._closed)

        frm = ttk.Frame(self, padding=20)
        frm.grid(sticky="nsew")
        frm.columnconfigure(0, weight=1)

        self._heading = ttk.Label(frm, font=("TkDefaultFont", 15, "bold"))
        self._heading.grid(row=0, column=0, sticky="w")

        self._bar = ttk.Progressbar(frm, mode="indeterminate", length=380)
        self._detail = ttk.Label(frm, foreground="#666")
        self._canvas = tk.Canvas(frm, width=430, height=118, highlightthickness=0)
        self._instr = ttk.Label(frm, wraplength=400, justify="left")

        try:
            self._canvas.configure(bg=self.cget("background"))
        except tk.TclError:
            pass
        self._art_fg, self._art_acc = self._art_colours()

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, sticky="ew", pady=(18, 0))
        btns.columnconfigure(0, weight=1)
        self._cancel_btn = _button(btns, "Cancel print", _RED, self._cancel)
        self._primary_btn = _button(btns, "", _BLUE, self._primary)
        self._cancel_btn.grid(row=0, column=0, sticky="w")
        self._primary_btn.grid(row=0, column=1, sticky="e")

        self.bind("<Return>", lambda _e: self._primary())
        self.bind("<Escape>", lambda _e: self._cancel())

        self._center_on(parent)
        self.after(0, self._grab)

    # ---- public API ------------------------------------------------
    @property
    def phase(self) -> str | None:
        return self._phase

    def show_phase(self, phase: str, *, heading: str | None = None,
                   detail: str | None = None, instruction: str | None = None) -> None:
        self._phase = phase
        for w in (self._bar, self._detail, self._canvas, self._instr):
            w.grid_remove()
        self._bar.stop()

        self._heading.configure(text=heading or _HEADING[phase],
                                foreground=_HEADING_FG.get(phase, ""))

        if phase in (PREPARING, PRINTING):
            self._bar.grid(row=2, column=0, sticky="ew", pady=(16, 6))
            self._bar.start(_BAR_MS)
            if detail:
                self._detail.configure(text=detail)
                self._detail.grid(row=3, column=0, sticky="w")
        elif phase == FLIP:
            self._draw_flip_art()
            self._canvas.grid(row=2, column=0, pady=(16, 10))
            self._instr.configure(text=instruction or FLIP_INSTRUCTION)
            self._instr.grid(row=3, column=0, sticky="w")
        elif detail:  # terminal with a message
            self._detail.configure(text=detail)
            self._detail.grid(row=2, column=0, sticky="w", pady=(12, 0))

        active = phase in _ACTIVE
        (self._cancel_btn.grid if active else self._cancel_btn.grid_remove)()
        self._cancel_btn.configure(state="normal")

        if phase == FLIP:
            _recolour(self._primary_btn, _GREEN)
            self._primary_btn.configure(text="Continue — print the back side")
            self._primary_btn.grid()
            self._primary_btn.focus_set()
        elif phase in _TERMINAL:
            _recolour(self._primary_btn, _BLUE)
            self._primary_btn.configure(text="Close")
            self._primary_btn.grid()
            self._primary_btn.focus_set()
        else:
            self._primary_btn.grid_remove()

        self._center_on(self.master)

    def set_detail(self, text: str) -> None:
        self._detail.configure(text=text)

    def disable_cancel(self) -> None:
        self._cancel_btn.configure(state="disabled")

    def enable_cancel(self) -> None:
        self._cancel_btn.configure(state="normal")

    def bring_forward(self) -> None:
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.after(500, lambda: self._safe_attr("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    # ---- callbacks ------------------------------------------------
    def _primary(self) -> None:
        if self._phase == FLIP:
            self._on_continue()
        elif self._phase in _TERMINAL:
            self._on_close()

    def _cancel(self) -> None:
        if self._phase in _ACTIVE:
            self._on_cancel()

    def _closed(self) -> None:
        if self._phase in _TERMINAL:
            self._on_close()
        elif self._phase in _ACTIVE:
            self._on_cancel()

    # ---- internals -------------------------------------------------
    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            self.after(80, self._grab_retry)

    def _grab_retry(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _safe_attr(self, name: str, value) -> None:
        try:
            self.attributes(name, value)
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

    def _art_colours(self) -> tuple[str, str]:
        try:
            r, g, b = self._canvas.winfo_rgb(self._canvas.cget("bg"))
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 257
            if lum < 128:
                return "#dcdcdc", "#9db1e6"
        except tk.TclError:
            pass
        return "#555555", "#2b3a67"

    def _draw_flip_art(self) -> None:
        c = self._canvas
        c.delete("all")
        fg, acc = self._art_fg, self._art_acc
        bg = c.cget("bg")
        cy = 48

        def printer(cx: int) -> None:
            c.create_rectangle(cx - 22, cy - 6, cx + 22, cy + 14, outline=fg, width=2)
            c.create_rectangle(cx - 12, cy - 16, cx + 12, cy - 6, outline=fg, width=2)
            c.create_rectangle(cx - 12, cy + 14, cx + 12, cy + 27, outline=fg, width=2, fill=bg)
            c.create_line(cx + 12, cy + 2, cx + 18, cy + 2, fill=fg, width=2)

        def connector(x1: int, x2: int) -> None:
            c.create_line(x1, cy, x2, cy, fill=fg, width=2, arrow="last",
                          arrowshape=(9, 10, 4))

        def arc_head(fx: int, fy: int, r: int, ang: float) -> None:
            a1, a2 = math.radians(ang - 7), math.radians(ang)
            c.create_line(fx + r * math.cos(a1), fy - r * math.sin(a1),
                          fx + r * math.cos(a2), fy - r * math.sin(a2),
                          fill=acc, width=2, arrow="last", arrowshape=(8, 9, 4))

        printer(38)
        connector(64, 150)

        fx, fy, r = 215, cy, 30
        c.create_arc(fx - r, fy - r, fx + r, fy + r, start=28, extent=196,
                     style="arc", outline=acc, width=2)
        c.create_arc(fx - r, fy - r, fx + r, fy + r, start=208, extent=196,
                     style="arc", outline=acc, width=2)
        arc_head(fx, fy, r, 28 + 196)
        arc_head(fx, fy, r, 208 + 196)
        c.create_rectangle(fx - 13, fy - 19, fx + 13, fy + 19, outline=acc, width=2, fill=bg)
        c.create_line(fx + 5, fy - 19, fx + 5, fy - 11, fx + 13, fy - 11, fill=acc, width=1)  # dog-ear

        connector(280, 366)
        printer(392)

        for x, label in ((38, "print side 1"), (215, "flip the stack"), (392, "print side 2")):
            c.create_text(x, cy + 44, text=label, font=("TkDefaultFont", 10),
                          fill=acc if label == "flip the stack" else fg)
