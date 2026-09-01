"""Flat, colour-filled buttons that actually render their colour on macOS.

`tk.Button` on the macOS aqua theme ignores `background` while enabled
(it draws the native button face), so a coloured button built that way
shows grey when clickable. This `Button` is a `tk.Label` with click /
hover / focus bindings — Labels honour `background` on every platform.
"""

from __future__ import annotations

import tkinter as tk

GREEN = "#2f8f4e"
RED = "#c0392b"
BLUE = "#2b5fb0"


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    clamp = lambda v: max(0, min(255, int(round(v))))
    return f"#{clamp(r):02x}{clamp(g):02x}{clamp(b):02x}"


def darken(colour: str, factor: float = 0.82) -> str:
    r, g, b = _rgb(colour)
    return _hex(r * factor, g * factor, b * factor)


def _fade(colour: str, t: float = 0.55) -> str:
    """Blend toward white — the disabled / not-yet-available look."""
    r, g, b = _rgb(colour)
    return _hex(r + (255 - r) * t, g + (255 - g) * t, b + (255 - b) * t)


class Button(tk.Label):
    def __init__(self, parent, text: str, colour: str, command, *, big: bool = False):
        super().__init__(
            parent, text=text, bg=colour, fg="white", font="TkDefaultFont",
            padx=20 if big else 16, pady=9 if big else 7,
            cursor="pointinghand", takefocus=True,
            highlightthickness=2, highlightbackground=colour,
            highlightcolor=darken(colour, 0.55),
        )
        self._command = command
        self._colour = colour
        self._enabled = True
        for seq, fn in (
            ("<Button-1>", self._press), ("<ButtonRelease-1>", self._release),
            ("<Enter>", self._hover), ("<Leave>", self._unhover),
            ("<Return>", self._key), ("<space>", self._key),
            ("<FocusIn>", self._focus), ("<FocusOut>", self._unfocus),
        ):
            self.bind(seq, fn)

    # ---- painting ------------------------------------------------
    def _paint(self, colour: str) -> None:
        tk.Label.configure(self, bg=colour, highlightbackground=colour)

    def recolour(self, colour: str) -> None:
        self._colour = colour
        if self._enabled:
            self._paint(colour)
            tk.Label.configure(self, fg="white")

    # ---- events -------------------------------------------------
    def _press(self, _e):
        if self._enabled:
            self._paint(darken(self._colour, 0.68))

    def _release(self, e):
        if not self._enabled:
            return
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self._paint(darken(self._colour) if inside else self._colour)
        if inside and self._command:
            self._command()

    def _hover(self, _e):
        if self._enabled:
            self._paint(darken(self._colour))

    def _unhover(self, _e):
        if self._enabled:
            self._paint(self._colour)

    def _key(self, _e):
        if self._enabled and self._command:
            self._command()
        return "break"

    def _focus(self, _e):
        tk.Label.configure(self, highlightbackground=darken(self._colour, 0.55))

    def _unfocus(self, _e):
        tk.Label.configure(self, highlightbackground=self._colour)

    # ---- tk.Button-compatible surface ---------------------------
    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") in ("normal", tk.NORMAL)
            if self._enabled:
                self._paint(self._colour)
                tk.Label.configure(self, fg="white", cursor="pointinghand")
            else:
                faded = _fade(self._colour)
                tk.Label.configure(self, bg=faded, highlightbackground=faded,
                                   fg="#f4f6fa", cursor="")
        if "text" in kw:
            tk.Label.configure(self, text=kw.pop("text"))
        if kw:
            tk.Label.configure(self, **kw)

    config = configure


def button(parent, text: str, colour: str, command, *, big: bool = False) -> Button:
    return Button(parent, text, colour, command, big=big)


def recolour(btn: Button, colour: str) -> None:
    btn.recolour(colour)
