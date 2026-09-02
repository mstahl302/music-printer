# Feature Spec — Register as a PDF Handler ("Open With")

**Feature:** #20 in [feature_requests.md](feature_requests.md)
**Status:** DRAFT — not yet built.
**Date:** 2026-09-02

---

## 1. Summary

Make **Music Printer** show up in a PDF's right-click **Open With** submenu
in Finder, and accept the file when chosen. Selecting one or more PDFs and
opening them with Music Printer should land those files in the main
window's list — exactly as if they had been added through **Add PDFs…** —
whether the app was closed or already running.

Three moving parts:

1. **Bundle declaration.** The `.app` advertises "I open PDFs" via
   `CFBundleDocumentTypes` in its `Info.plist`, plus a stable
   `CFBundleIdentifier` for Launch Services to key on.
2. **Event receipt.** The running process catches the
   `kAEOpenDocuments` Apple Event through Tk's
   `::tk::mac::OpenDocument` command and routes the paths into the
   existing file-list flow.
3. **Registration.** After a build, Launch Services has to be told the new
   handler exists (`lsregister`, or just moving the app to `/Applications`
   and launching it once).

No new runtime dependency. The work is in the build (`build.sh`), a small
amount of wiring in `main.py`, and documentation.

## 2. Problem / value

Adding music to the app today is always: launch Music Printer → **Add
PDFs…** → navigate to the folder → select. But the user is very often
*already looking at the PDF in Finder* (that's where a Musicnotes download
lands). The natural gesture — right-click the file, "Open With Music
Printer" — does nothing, because the app never told macOS it can handle
PDFs.

**Value:** collapses "find the app, then find the file" into one
right-click from where the file already is. It also makes multi-select
work from Finder: shift-click a Sunday's worth of PDFs, Open With Music
Printer, and the set-list is populated in performance order without a
single trip through the open panel. For a non-technical choir user this is
the difference between a tool they have to go *to* and one that's just
*there* on the file.

## 3. Non-goals

- **Not the default PDF app.** Music Printer must never displace Preview
  as the default double-click handler. It offers itself in the *Open
  With* submenu only (`LSHandlerRank: Alternative`). If the user really
  wants it as the default they can still do Get Info → Open With → Change
  All themselves; the app doesn't ask for or nudge toward that.
- **No other file types.** PDF (`com.adobe.pdf`) only. Not images, not
  MusicXML, not `.mxl`.
- **No drag-and-drop onto the window or Dock icon.** That's a separate
  mechanism (`tk::mac::OpenDocument` covers the Dock-icon drop for free,
  but window drop needs `tkdnd` / a native view and is out of scope).
- **No "print immediately on open" mode.** Opening files fills the list
  and stops there; the user still reviews the list and clicks **Preview**
  / **Start**. (A future "open and print" is noted in §9.)
- **No `argv_emulation`.** PyInstaller's `argv_emulation=True` shim only
  catches the launch-time file and has a history of flakiness with Tk;
  the Apple Event handler is the correct tool for a Tk app and handles
  both cold and warm opens.

## 4. Piece 1 — declare PDF support in the bundle

macOS reads document types from the app's `Info.plist`. Two keys matter:

| Key | Value | Why |
|---|---|---|
| `CFBundleIdentifier` | `io.github.mstahl302.music-printer` | Launch Services keys every handler by bundle id. The current build sets **none** — this must be added first or registration has nothing to hang on. |
| `CFBundleDocumentTypes` | one entry, below | The actual "I can open these" declaration. |

```
CFBundleDocumentTypes = [{
    'CFBundleTypeName'  : 'PDF document',
    'LSItemContentTypes': ['com.adobe.pdf'],
    'CFBundleTypeRole'  : 'Viewer',
    'LSHandlerRank'     : 'Alternative',
}]
```

- **`LSHandlerRank: Alternative`** is the whole game — it puts Music
  Printer in the *Open With* submenu **without** competing with Preview
  for the default. `Owner` or `Default` would try to take over
  double-click, which §3 forbids.
- **`CFBundleTypeRole: Viewer`** (not `Editor`) — the app consumes the
  PDF, it doesn't save changes back to it.
- `LSItemContentTypes` with the UTI `com.adobe.pdf` is the modern form;
  no need for the legacy `CFBundleTypeExtensions` / `CFBundleTypeMIMETypes`.

### 4.1 How it gets into the plist — build change

`build.sh` today runs `pyinstaller main.py` with plain CLI flags
(`--windowed --icon … --name …`). The PyInstaller CLI has **no option**
for `CFBundleDocumentTypes` or a custom bundle id, so the build has to
change. Two options:

- **A — checked-in `.spec` file (preferred).** Generate
  `Music Printer.spec` once (`pyi-makespec` from the current flags), add
  `bundle_identifier=` and `info_plist={...}` to its `BUNDLE(...)` call,
  commit it, and change `build.sh` to run `pyinstaller "Music Printer.spec"`.
  This is the standard PyInstaller way to control the bundle and keeps the
  plist under version control next to the icon. Cost: a ~40-line generated
  file enters the repo and now has to be kept in sync by hand if the build
  flags ever change.
- **B — post-build plist patch.** Keep the CLI build; after it, patch
  `dist/Music Printer.app/Contents/Info.plist` in `build.sh` with
  `/usr/libexec/PlistBuddy` (add the bundle id + document-types array).
  Smaller diff, no new tracked file, but the plist keys live as shell
  heredoc in `build.sh` instead of as data, and it's easy to forget the
  patch step exists.

**Recommendation:** A. The `.spec` file is where this kind of bundle
metadata is meant to live, and `run.sh` / `build.sh` already assume a
one-command build. Decide at review (§8).

### 4.2 Icon for the document type

Optional, low priority: `CFBundleTypeIconFile` can point at an `.icns` so
PDFs "belonging to" Music Printer get a badged icon in Finder. Skip for
v1 — it needs a second icon asset and only shows when the app is the
*default* handler, which §3 rules out anyway.

## 5. Piece 2 — receive the file path

For a `.app` bundle, macOS does **not** put opened paths in `sys.argv` —
it sends a `kAEOpenDocuments` Apple Event. Tk surfaces this as a command
named `::tk::mac::OpenDocument`, the same createcommand mechanism the app
already uses for `tk::mac::Quit`
([main.py](../main.py) `App.__init__`, ~line 486).

### 5.1 Wiring

In `App.__init__`, next to the existing `tk::mac::Quit` registration:

```
self._pending_open: list[str] = []
try:
    self.createcommand("::tk::mac::OpenDocument", self._open_documents)
except tk.TclError:
    pass
```

Handler:

```
def _open_documents(self, *paths):
    pdfs = [p for p in paths
            if p.lower().endswith(".pdf") and Path(p).is_file()]
    if not pdfs:
        return
    if getattr(self, "filelist", None) is None:
        self._pending_open += pdfs          # AE arrived before _build()
    else:
        self._accept_opened(pdfs)
```

`_accept_opened(paths)` is the single choke point that both this and the
pending-flush call:

```
def _accept_opened(self, paths):
    if self.state != READY:
        # A run is in progress. Queue, don't disturb it.
        self._pending_open += paths
        self.bell()
        return
    self.deiconify(); self.lift(); self.focus_force()
    self.filelist.add(paths)                 # fires on_change -> _recompute
    self.cfg["last_folder"] = str(Path(paths[0]).parent)
    settings.save(self.cfg)
```

`self.filelist.add(...)` is exactly what **Add PDFs…** calls
([main.py](../main.py) `_pick_files`), so cover-strip detection, the
plan-worker thread, un-openable-file flagging, and the sheet-count status
line all happen with no extra code.

### 5.2 Flush after `_build()`

At the end of `_build()` (or right after `_load_printers()` in
`__init__`), drain the buffer:

```
if self._pending_open:
    pending, self._pending_open = self._pending_open, []
    self._accept_opened(pending)
```

Because `_build()` runs **synchronously inside `__init__`** today,
`self.filelist` will in practice exist by the time the first Apple Event
is dispatched (events pump only once `mainloop()` runs). The buffer is
cheap insurance against that ordering ever changing, and it's the same
buffer the "run in progress" case reuses.

### 5.3 Two entry scenarios, one path

| Scenario | What happens |
|---|---|
| **Cold** — app not running, user picks Open With | macOS launches the app, then sends `kAEOpenDocuments`. `__init__` runs, `_build()` builds the UI, buffer (if any) flushes, files land in the list. |
| **Warm** — app already open, user picks Open With again | `_open_documents` fires immediately; `_accept_opened` raises the window and appends to the existing list. Files **append**, they don't replace — opening song 6 after songs 1–5 are already staged extends the set. |

## 6. Piece 3 — register with Launch Services

A freshly built `.app` isn't consulted for document types until Launch
Services has scanned it. Normal path: **move it to `/Applications` and
launch it once** — LS registers it automatically.

To force it without moving (useful right after `build.sh`):

```bash
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "dist/Music Printer.app"
```

After that, a PDF's right-click **Open With** lists **Music Printer**.

This belongs in the docs, not the build — `build.sh` produces an
unsigned bundle in `dist/` that Gatekeeper blocks elsewhere anyway
(README "Build the .app"), so registration is a step the user does on the
machine where they actually install the app. Add a short **"Open PDFs
with Music Printer"** subsection to [../README.md](../README.md) and/or
[../USER_GUIDE.md](../USER_GUIDE.md):

> 1. Move **Music Printer.app** to your **Applications** folder and open
>    it once.
> 2. In Finder, right-click any PDF → **Open With** → **Music Printer**.
>    Select several PDFs first to add a whole set at once.
> 3. (Optional, not recommended) To make it the default for every PDF:
>    Get Info on a PDF → *Open with* → Music Printer → **Change All**.

## 7. Edge cases

| Case | Behaviour |
|---|---|
| **Non-PDF passed** (someone selects a mix and Opens With) | Filtered out in `_open_documents` by extension + `is_file()`. If nothing survives, do nothing (no error dialog). |
| **File is missing / unreadable by the time we look** | `Path(p).is_file()` filter drops it. A file that opens but is encrypted or 0-page is handled downstream by the existing plan worker, which flags it **⚠ Can't open this PDF** in the row and blocks Preview until removed (spec_batch_printing §5.1). No new handling. |
| **Open With while a print run is active** (`state != READY`) | Files are buffered into `_pending_open`, a `bell()` sounds, the run is **not** interrupted. The buffer flushes when the run returns to READY. (Alternative considered: silently append to the list behind the modal run dialog. Rejected — the list isn't visible mid-run, so it'd be a silent no-feedback action. Flag at review §8.) |
| **Duplicate file opened** | Goes through `filelist.add()` — de-duplication is whatever that method already does; not changed here. |
| **Many files at once** | `kAEOpenDocuments` delivers them in one call as multiple `paths` args; `filelist.add()` takes a list. Finder generally preserves the selection's sort order. No cap. |
| **Second `.app` copy exists** (e.g. one in `dist/`, one in `/Applications`) | Launch Services picks one by its own rules (usually most recently registered). Documented caveat, not a code concern: tell users to keep a single copy in `/Applications`. |
| **Open With triggers a second app instance** | Shouldn't — LS routes the AE to the running instance. If a stale/dead instance ever caused a second launch, that's a pre-existing single-instance question, out of scope here. |

## 8. Open questions for review

1. **Build mechanism** — checked-in `Music Printer.spec` (§4.1 A) vs.
   post-build PlistBuddy patch in `build.sh` (§4.1 B). Recommendation: A.
2. **Bundle identifier string** — `io.github.mstahl302.music-printer`
   assumed (matches the GitHub repo `mstahl302/music-printer`). Confirm,
   since it's effectively permanent once shipped — changing it later
   makes Launch Services treat it as a different app.
3. **Open With during an active run** — buffer + `bell()` + flush on
   READY (proposed), vs. silently append, vs. a small non-modal toast.
4. **Warm open = append vs. replace** — proposed **append** (extends the
   set). Confirm that's the wanted behaviour and not "replace the list
   with what I just opened".
5. **Raise / focus on warm open** — `deiconify` + `lift` + `focus_force`
   proposed so the window comes forward when you Open With from Finder.
   `focus_force` is mildly aggressive; acceptable here?
6. **Bundle version keys** — while touching the plist, also set
   `CFBundleShortVersionString` / `CFBundleVersion` from a single source?
   Adjacent cleanup, could fold in or leave for its own change.

## 9. Later / adjacent (not this spec)

- **Open-and-print** — a modifier or a setting so Open With goes straight
  to the Preview dialog (or even straight to Start) for the
  one-file-one-print case.
- **Drag PDFs onto the window** — needs `tkdnd` or a native drop view.
- **Recent files** — an "Open Recent" menu of previously printed sets;
  natural companion to saved set-lists (feature_requests #11).
- **Document icon badge** — `CFBundleTypeIconFile` (§4.2) once there's a
  reason to.

## 10. Build outline

| Piece | Change |
|---|---|
| `build.sh` | switch to a checked-in `Music Printer.spec` (or add a PlistBuddy patch step). Set `CFBundleIdentifier` + `CFBundleDocumentTypes` (PDF, `Viewer`, `Alternative`). |
| `Music Printer.spec` (new, if option A) | generated from current flags; `BUNDLE(..., bundle_identifier=…, info_plist={…})`. |
| `main.py` | `createcommand("::tk::mac::OpenDocument", self._open_documents)` beside the existing `tk::mac::Quit`; add `_open_documents`, `_accept_opened`, `_pending_open` buffer; flush the buffer at the end of `_build()`. ~25 lines. |
| `README.md` / `USER_GUIDE.md` | new "Open PDFs with Music Printer" section — move to `/Applications`, launch once, right-click → Open With; the `lsregister -f` one-liner for a `dist/` build. |
| `tests/` | `test_flow.py`: call `app._open_documents("/path/a.pdf", "/path/b.pdf")` and assert both reach `app.filelist`; a call while `app.state != READY` buffers and does not change state; the buffer flushes on return to READY. Reuse the existing sample PDFs. No new infra. |
| reuses | `FileList.add`, `_recompute` / plan worker, cover detection, un-openable-file flagging, settings `last_folder`. |

No prerequisite features. Batch/set-list (feature #2) is already built, so
multi-file Open With works the moment the paths reach `filelist.add()`.
