# Music Printer

![tests](https://github.com/mstahl302/music-printer/actions/workflows/ci.yml/badge.svg)

A tiny macOS GUI that prints **double-sided sheet music on a single-sided
printer**: it prints the even pages, waits for the printer, has you flip
the stack, then prints the odd pages onto the backs — removing vendor
cover sheets and padding odd page counts along the way.

**Using the app?** See the **[User's Guide](USER_GUIDE.md)** for the
problem it solves and a step-by-step walkthrough. This file is for
building and developing it.

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

Full design: [docs/specification.md](docs/specification.md).
Cover-detection heuristics: [docs/cover_signals.md](docs/cover_signals.md).

## Setup

Needs **Python 3.14** (python.org build, for Tk 9 — the system
`/usr/bin/python3` is 3.9 / Tk 8.5 and won't work). Get the macOS
universal2 installer from <https://www.python.org/downloads/macos/>, then:

```bash
git clone https://github.com/mstahl302/music-printer.git
cd music-printer
python3.14 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

(`requirements.txt` alone is enough to *run* the app; `-dev` adds
PyInstaller and pytest.)

## Develop

```bash
source .venv/bin/activate
python main.py
```

## Test

```bash
source .venv/bin/activate
python -m pytest
```

The suite covers the page-planning math, cover detection against
synthetic PDFs, and the full two-pass state machine (with printing
mocked). CI runs it on every push.

## Build the .app

```bash
source .venv/bin/activate
./build.sh
open "dist/Music Printer.app"
```

Produces `dist/Music Printer.app`, which runs on the machine that built
it.

## Distributing to other Macs

A bare PyInstaller build runs here but Gatekeeper blocks it elsewhere. To
share it: Apple Developer account ($99/yr), then `codesign` with a
"Developer ID Application" cert, `xcrun notarytool submit`, `xcrun
stapler staple`, ship in a `.dmg`. Not needed for personal use.

## Implementation notes

- **Printing** goes through the built-in `lp` / `lpstat` / `cancel`
  command-line tools — no third-party print libraries. The app tracks
  each pass to completion and only prompts for the flip once pass 1 has
  actually finished.
- Behavioral assumptions (printer page-reversal, flip edge, etc.) and
  where settings/logs live are documented for end users in the
  [User's Guide](USER_GUIDE.md#notes-and-assumptions).

## Licence

MIT — see [LICENSE](LICENSE).
