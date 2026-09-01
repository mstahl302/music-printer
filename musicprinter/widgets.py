"""Shared flat, colour-filled buttons.

ttk buttons ignore ``background`` on macOS aqua; a ``tk.Button`` with
``relief="flat"`` and an explicit ``bg`` does not.
"""

from __future__ import annotations

import tkinter as tk

GREEN = "#2f8f4e"
RED = "#c0392b"
BLUE = "#2b5fb0"
BLUE_FADED = "#9fb6d9"   # disabled / not-yet-available


def darken(hex_colour: str, factor: float = 0.82) -> str:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def button(parent, text: str, colour: str, command, *, big: bool = False) -> tk.Button:
    return tk.Button(
        parent, text=text, command=command,
        bg=colour, fg="white",
        activebackground=darken(colour), activeforeground="white",
        disabledforeground="#eef1f6", highlightbackground=colour,
        relief="flat", borderwidth=0, highlightthickness=0,
        cursor="pointinghand", font="TkDefaultFont",
        padx=20 if big else 16, pady=9 if big else 7,
    )


def recolour(btn: tk.Button, colour: str) -> None:
    btn.configure(bg=colour, activebackground=darken(colour), highlightbackground=colour)
