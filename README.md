# Music Printer

![tests](https://github.com/mstahl302/music-printer/actions/workflows/ci.yml/badge.svg)

A tiny macOS GUI that prints **double-sided sheet music on a single-sided
printer**. Pick a printer and a PDF, hit Start: the app prints the even
pages, waits for the printer, asks you to flip the stack (short edge), then
prints the odd pages onto the backs. It also removes vendor cover sheets
(Musicnotes) and inserts a blank pad sheet when the page count is odd.

Full design: [docs/specification.md](docs/specification.md).
Cover-detection heuristics: [docs/cover_signals.md](docs/cover_signals.md).

```
main.py                  Tkinter UI + two-pass state machine
musicprinter/
  duplex.py              pure page planning (EVEN/ODD passes, blank pad)
  covers/                vendor cover-sheet detection (extensible registry)
    base.py                shared types + page-structure helpers
    musicnotes.py          Musicnotes cover detector
  pdfio.py               inspect / thumbnail / build per-pass PDFs
  jobs.py                source PDF + mode -> concrete Plan
  printing.py            CUPS submit / track / cancel (lp / lpstat / cancel)
  settings.py            persisted settings + log
tests/                   pytest: page math, cover detection, flow state machine
build.sh                 produces "dist/Music Printer.app"
```

## Setup

Python 3.14 (python.org build, Tk 9) is already installed. Then:

```
cd ~/music-printer
python3.14 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Develop

```
source .venv/bin/activate
python main.py
```

## Test

```
source .venv/bin/activate
python -m pytest
```

## Build the .app

```
source .venv/bin/activate
./build.sh
open "dist/Music Printer.app"
```

## Runtime notes

- **Printing** goes through the built-in `lp` / `lpstat` / `cancel` tools.
  The app tracks each pass to completion and only prompts for the flip
  once pass 1 has actually finished.
- **Fixed assumptions** (see spec §7.4): the printer reverses PDF page
  order on output, the flip is about the short edge, no back-side
  rotation, no scaling. These match the owner's setup and are not
  configurable in v1.
- **Settings / log** live in
  `~/Library/Application Support/Music Printer/`.

## Distributing to other Macs

A bare PyInstaller build runs here but Gatekeeper blocks it elsewhere. To
share it: Apple Developer account ($99/yr), then `codesign` with a
"Developer ID Application" cert, `xcrun notarytool submit`, `xcrun
stapler staple`, ship in a `.dmg`. Not needed for personal use.
