# Music Printer

![tests](https://github.com/mstahl302/music-printer/actions/workflows/ci.yml/badge.svg)

A small macOS app that prints **double-sided sheet music on a single-sided
printer**. It prints one side of every sheet, waits for the printer, asks
you to flip the stack, then prints the other side onto the backs — so you
end up with a correctly ordered, correctly collated double-sided copy.

---

## The problem

Choir and vocal folders fill up fast, and single-sided sheet music is
twice the paper and twice the page turns. Plenty of printers can't do
duplex, and the ones that can often mangle the page order for a booklet.

Doing it by hand works but is fiddly:

- You print the even pages, flip the stack, and print the odd pages onto
  the backs. Get the order or the flip wrong and you reprint.
- When a song has an **odd** number of pages, the two halves don't match —
  the odd side needs one more sheet than the even side, so you have to
  slip in a blank by hand or the last page lands on the wrong side.
- Sheet music bought from **Musicnotes** usually arrives with a **cover
  page** (title, licence text) as page 1. Printing it wastes a sheet and
  throws off the even/odd split for everything after it.

Music Printer automates exactly that workflow.

## How it works

The owner's printer reverses PDF page order on output, and the flip is
about the short edge — given that, this sequence produces reading order
(the full derivation is in [docs/specification.md](docs/specification.md),
Appendix A):

1. **Pass 1 — even pages.** The app sends effective pages 2, 4, 6, … If the
   song has an odd page count, it appends **one blank page** so the two
   passes use the same number of sheets.
2. **Flip.** The app waits until the printer has actually finished, then
   prompts you to take the stack out, flip it about the short edge, and
   put it back in the tray.
3. **Pass 2 — odd pages.** The app sends effective pages 1, 3, 5, … which
   print onto the blank backs.

"Effective pages" means *after* any cover sheet is removed — page numbering
is recomputed so the split still lands correctly.

A single-page song skips the flip and just prints.

---

## Installation

Music Printer needs **Python 3.14** with a modern Tk. The system Python at
`/usr/bin/python3` (3.9, Tk 8.5) will not work.

1. **Install Python** from python.org — the macOS 64-bit universal2
   installer (currently 3.14.x): <https://www.python.org/downloads/macos/>.
   After it installs, `python3.14` is on your `PATH`.

2. **Clone and set up a virtual environment:**

   ```bash
   git clone https://github.com/mstahl302/music-printer.git
   cd music-printer
   python3.14 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements-dev.txt
   ```

   (`requirements.txt` alone is enough to *run* the app; the `-dev` file
   adds PyInstaller and pytest.)

## Running from source

```bash
source .venv/bin/activate
python main.py
```

## Building a standalone .app

```bash
source .venv/bin/activate
./build.sh
open "dist/Music Printer.app"
```

This produces `dist/Music Printer.app`, which runs on the machine that
built it. To hand it to someone else you need an Apple Developer account
and must code-sign and notarize it — see [README.md](README.md).

---

## User's guide

### 1. Choose a printer

Pick from the dropdown (your system default is preselected). If the
printer is paused, the app tells you — jobs will queue but not print until
you resume it.

### 2. Choose a PDF

Click **Choose PDF…** and pick a sheet music file. Password-protected
PDFs aren't supported.

### 3. Choose how to handle a cover sheet

| Mode | What it does |
|---|---|
| **Smart (detect)** — default | Removes page 1 only if it looks like a vendor cover: no engraved music on the page *and* Musicnotes licence boilerplate text. Conservative — when in doubt it keeps the page. |
| **Always remove first page** | Drops page 1 unconditionally (unless the file is a single page). |
| **Don't remove** | Prints the PDF exactly as-is. |

The detection signals are documented in
[docs/cover_signals.md](docs/cover_signals.md).

### 4. Read the plan preview

The preview shows:

- a **thumbnail of what will become page 1** (after any cover removal) —
  glance at it to confirm the strip did the right thing;
- **sheets of music to print** (the effective page count);
- the **cover decision** in one line;
- **sheets of paper to prepare** — how many to load in the tray. If the
  count is odd, it notes that a blank sheet is added automatically.

### 5. Start

Click **Start**. The app builds a temporary PDF for pass 1, sends it, and
tracks the job:

```
Queued  →  Printing…  →  Pass 1 finished
```

### 6. Flip when prompted

When pass 1 is done, the app shows:

> Pass 1 is done. Take the printed stack out, flip it about the SHORT
> edge, and put it back in the tray. Then click below.

Do that, then click **"Pages are flipped — print pass 2"**.

### 7. Done

After pass 2 finishes you get a confirmation and a **Print another**
button, which resets everything but keeps your printer selection.

### Cancelling

The **Cancel** button is active whenever a pass is printing or the app is
waiting for the flip:

- **During pass 1** — cancels the job, returns to the start. Nothing else
  prints.
- **While waiting to flip** — asks to confirm, then stops. The pass 1
  sheets are already printed.
- **During pass 2** — cancels the job. Some sheets will be printed on one
  side only.

---

## Notes and assumptions

- **Fixed for this version:** the printer reverses PDF page order on
  output, the flip is short-edge, no back-side rotation, and pages print
  at 100 % (no scaling). These match the author's setup and aren't
  configurable yet.
- **Settings and a log** are kept in
  `~/Library/Application Support/Music Printer/`.
- **Printing** uses the built-in `lp` / `lpstat` / `cancel` command-line
  tools; no third-party print libraries.

## Development

```bash
source .venv/bin/activate
python -m pytest
```

The suite covers the page-planning math, cover detection against
synthetic PDFs, and the full two-pass state machine (with printing
mocked). CI runs it on every push.

- Design: [docs/specification.md](docs/specification.md)
- Cover-detection heuristics: [docs/cover_signals.md](docs/cover_signals.md)

## Licence

MIT — see [LICENSE](LICENSE).
