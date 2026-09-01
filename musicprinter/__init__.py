"""Music Printer — duplex sheet music on a simplex printer.

- :mod:`musicprinter.duplex`   — pure page planning (EVEN/ODD passes, blank pad)
- :mod:`musicprinter.covers`   — vendor cover-sheet detection
- :mod:`musicprinter.pdfio`    — inspect / thumbnail / build per-pass PDFs
- :mod:`musicprinter.jobs`     — source PDF + mode -> concrete Plan
- :mod:`musicprinter.printing` — CUPS submit / track / cancel
- :mod:`musicprinter.settings` — persisted settings + log

The Tkinter UI and the two-pass state machine live in ``main.py``.
"""

__version__ = "0.2.0"
