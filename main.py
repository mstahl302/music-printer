#!/usr/bin/env python3
"""Music Printer — Tkinter front-end and two-pass state machine.

Pick a printer and a PDF, choose how to handle a vendor cover sheet, hit
Start. A modal run dialog then owns the run: it prints the EVEN pages,
waits for the printer, asks you to flip the stack (short edge), and prints
the ODD pages onto the backs. See docs/specification.md and
docs/spec_guided_print_dialog.md.
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

from musicprinter import jobs, printing, rundialog, settings
from musicprinter.pdfio import PdfError

# UI label  ->  strip mode
COVER_MODES = {
    "Always Remove First Page": "always",
    "Don't Remove": "none",
    "Smart Strip (remove if detected)": "smart",
}
MODE_TO_LABEL = {v: k for k, v in COVER_MODES.items()}
DEFAULT_COVER_LABEL = "Smart Strip (remove if detected)"

FLIP_SOUND = "/System/Library/Sounds/Ping.aiff"

# how often to poll CUPS for job status (ms) — lowered by the test suite
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

_PASS_HEADING = {
    "even": "Printing — pass 1 of 2",
    "odd": "Printing — pass 2 of 2",
    "single": "Printing",
}
_PASS_SIDE = {"even": "Even pages", "odd": "Odd pages", "single": "Pages"}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Music Printer")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cfg = settings.load()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="music-printer-"))
        self._q: queue.Queue = queue.Queue()

        # inputs
        self.printer = tk.StringVar(value=self.cfg["last_printer"])  # real CUPS queue name
        self.printer_display = tk.StringVar(value="")                # friendly text on the button
        self._printers: dict[str, printing.Printer] = {}
        self.cover_label = tk.StringVar(
            value=MODE_TO_LABEL.get(self.cfg["strip_mode"], DEFAULT_COVER_LABEL))
        self.source_path: Path | None = None

        # derived
        self.plan: jobs.Plan | None = None
        self._plan_token = 0
        self._thumb_img: tk.PhotoImage | None = None

        # run state
        self.state = READY
        self.dialog: rundialog.RunDialog | None = None
        self._job_id: str | None = None
        self._gone_polls = 0
        self._canceling = False
        self._pass: str = ""

        # main-window display
        self.printer_warn = tk.StringVar(value="")
        self.preview_text = tk.StringVar(value="Choose a printer and a PDF.")

        self._build()
        self._load_printers()
        self.after(80, self._pump)

    # ================================================================ layout
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

        ttk.Button(frm, text="Choose PDF…", command=self._pick_file).grid(
            row=2, column=0, sticky="w", **pad)
        self.file_label = ttk.Label(frm, text="No file chosen", width=44, anchor="w")
        self.file_label.grid(row=2, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(frm, text="Strip Cover Sheet:").grid(row=3, column=0, sticky="w", **pad)
        self.cover_menu = ttk.OptionMenu(
            frm, self.cover_label, self.cover_label.get(), *COVER_MODES,
            command=lambda _=None: self._recompute_plan())
        self.cover_menu.grid(row=3, column=1, columnspan=2, sticky="ew", **pad)

        prev = ttk.LabelFrame(frm, text="Plan", padding=10)
        prev.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        prev.columnconfigure(1, weight=1)
        self.thumb_label = ttk.Label(prev, text="(no preview)", width=20,
                                     anchor="center", relief="solid", borderwidth=1)
        self.thumb_label.grid(row=0, column=0, rowspan=2, padx=(0, 12), pady=2, sticky="n")
        ttk.Label(prev, textvariable=self.preview_text, justify="left",
                  anchor="w").grid(row=0, column=1, sticky="nw")

        self.start_btn = ttk.Button(frm, text="Start", command=self._start)
        self.start_btn.grid(row=5, column=0, columnspan=3, **pad)

        self.another_btn = ttk.Button(frm, text="Print another", command=self._reset)
        self.another_btn.grid(row=5, column=0, columnspan=3, **pad)
        self.another_btn.grid_remove()

        self._set_state(READY)

    # ============================================================ printers
    def _load_printers(self) -> None:
        try:
            printers = printing.list_printers()
        except Exception as exc:
            self.preview_text.set(f"Could not list printers: {exc}")
            return
        self._printers = {p.name: p for p in printers}
        menu = self.printer_menu["menu"]
        menu.delete(0, "end")
        for p in printers:
            label = f"{p.label}  (default)" if p.is_default else p.label
            menu.add_command(label=label, command=lambda n=p.name: self._choose_printer(n))
        names = [p.name for p in printers]
        if self.printer.get() not in names:
            default = next((p.name for p in printers if p.is_default),
                           names[0] if names else "")
            self.printer.set(default)
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
        if p is None:
            self.printer_display.set(self.printer.get())
            return
        self.printer_display.set(f"{p.label}  (default)" if p.is_default else p.label)

    def _check_printer(self) -> None:
        name = self.printer.get()
        if name and printing.printer_state(name) == "disabled":
            self.printer_warn.set("This printer is paused — jobs will queue but not print.")
        else:
            self.printer_warn.set("")

    # ========================================================= file + plan
    def _pick_file(self) -> None:
        start = self.cfg["last_folder"] or str(Path.home())
        path = filedialog.askopenfilename(
            title="Choose sheet music (PDF)", initialdir=start,
            filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self.source_path = Path(path)
        self.file_label.config(text=self.source_path.name)
        self.cfg["last_folder"] = str(self.source_path.parent)
        settings.save(self.cfg)
        self._recompute_plan()

    def _recompute_plan(self) -> None:
        self.cfg["strip_mode"] = COVER_MODES[self.cover_label.get()]
        settings.save(self.cfg)
        if self.state != READY or self.source_path is None:
            return
        self.plan = None
        self._plan_token += 1
        token = self._plan_token
        self.preview_text.set("Reading PDF…")
        self._set_thumb(None)
        self._set_state(READY)
        threading.Thread(
            target=self._plan_worker,
            args=(token, self.source_path, self.cfg["strip_mode"],
                  float(self.cfg["confidence_threshold"])),
            daemon=True).start()

    def _plan_worker(self, token: int, path: Path, mode: str, threshold: float) -> None:
        try:
            plan = jobs.build_plan(path, mode, threshold=threshold)
            self._q.put(("plan", token, plan))
            try:
                from musicprinter import pdfio
                png = pdfio.render_thumbnail_png(path, plan.thumbnail_source_index0)
            except Exception:
                png = None
            self._q.put(("thumb", token, png))
        except PdfError as exc:
            self._q.put(("plan_err", token, str(exc)))
        except Exception as exc:  # unexpected
            self._q.put(("plan_err", token, f"Could not read this PDF: {exc}"))

    def _apply_plan(self, plan: jobs.Plan) -> None:
        self.plan = plan
        lines = [
            f"Sheets of music to print:  {plan.n_effective}",
            f"Cover: {plan.cover_summary()}",
        ]
        prep = f"Sheets of paper to prepare:  {plan.sheets_to_prepare}"
        if plan.passes.pad_blank:
            prep += "   (a blank sheet is added automatically on pass 1)"
        lines.append(prep)
        if plan.passes.single_pass and plan.n_effective <= 1:
            lines.append("Single page — prints in one pass, no flip needed.")
        self.preview_text.set("\n".join(lines))
        self._set_state(READY)

    def _set_thumb(self, png: bytes | None) -> None:
        if not png:
            self._thumb_img = None
            self.thumb_label.config(image="", text="(no preview)")
            return
        try:
            self._thumb_img = tk.PhotoImage(data=base64.b64encode(png).decode(), format="png")
            self.thumb_label.config(image=self._thumb_img, text="")
        except tk.TclError:
            self._thumb_img = None
            self.thumb_label.config(image="", text="(no preview)")

    # ================================================================ run
    def _start(self) -> None:
        if self.plan is None or not self.printer.get() or self.dialog is not None:
            return
        self._check_printer()
        if self.printer_warn.get() and not messagebox.askyesno(
                "Printer paused", f"{self.printer_warn.get()}\n\nQueue the job anyway?"):
            return

        self.dialog = rundialog.RunDialog(
            self, run_title=f"Printing — {self.source_path.name}",
            on_cancel=self._cancel, on_continue=self._start_pass2,
            on_close=self._close_dialog)
        self.dialog.show_phase(rundialog.PREPARING, detail="Building pass 1…")

        if self.plan.passes.single_pass:
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
        threading.Thread(
            target=self._submit_worker,
            args=(which, self.plan, self.printer.get()),
            daemon=True).start()

    def _submit_worker(self, which: str, plan: "jobs.Plan", printer_name: str) -> None:
        try:
            pdf = jobs.build_pass_pdf(plan, which, self._tmpdir)
            title = f"{plan.source_path.name} — {which}"
            reverse = bool(self.cfg.get("reverse_page_order", True))
            job_id = printing.submit(pdf, printer_name, title=title, reverse_order=reverse)
            settings.log(f"submit {which} job={job_id} file={pdf.name} "
                         f"pages={plan.n_effective} mode={plan.strip_mode} reverse={reverse}")
            self._q.put(("submitted", which, job_id))
        except Exception as exc:
            self._q.put(("submit_err", which, exc))

    def _detail(self, word: str) -> None:
        if self.dialog:
            self.dialog.set_detail(f"{_PASS_SIDE.get(self._pass, 'Pages')} · {word} · "
                                   f"job {self._job_id}")

    def _poll_job(self) -> None:
        if self.state not in _PRINTING or not self._job_id:
            return
        try:
            st = printing.job_status(self._job_id)
        except Exception as exc:
            self._finish_pass_failed(f"Lost track of the job: {exc}")
            return
        delay = _POLL_MS // 2 if self._canceling else _POLL_MS
        if st == "processing":
            self._detail("printing")
            self.after(delay, self._poll_job)
        elif st == "queued":
            self._detail("in the printer queue")
            self.after(delay, self._poll_job)
        elif st == "canceled" or (self._canceling and st in ("completed", "gone")):
            self._finish_pass_canceled()
        elif st == "aborted":
            self._finish_pass_failed(f"The printer aborted job {self._job_id}.")
        elif st == "completed":
            self._finish_pass_ok()
        else:  # gone — allow a few polls before trusting it
            self._gone_polls += 1
            if self._gone_polls >= 3:
                self._finish_pass_ok()
            else:
                self.after(delay, self._poll_job)

    # ---- pass outcomes ------------------------------------------------
    def _finish_pass_ok(self) -> None:
        settings.log(f"pass ok state={self.state} job={self._job_id}")
        self._job_id = None
        if self.state == PRINTING_PASS1:
            self._set_state(WAIT_FOR_FLIP)
            if self.dialog:
                self.dialog.show_phase(rundialog.FLIP)
                self.dialog.bring_forward()
            self._play_flip_cue()
        else:  # PASS2 or SINGLE
            self._set_state(DONE)
            if self.dialog:
                self.dialog.show_phase(rundialog.DONE, detail="Double-sided copy printed.")

    def _finish_pass_canceled(self) -> None:
        settings.log(f"pass canceled state={self.state} job={self._job_id}")
        was_pass2 = self.state == PRINTING_PASS2
        self._job_id = None
        self._set_state(DONE_ERROR if was_pass2 else READY)
        if self.dialog:
            detail = ("Some sheets are printed on one side only, and there may be "
                      "back-printed sheets still in the printer's feed tray — pull "
                      "those out before the next job.") if was_pass2 else ""
            self.dialog.show_phase(rundialog.CANCELLED, detail=detail)

    def _finish_pass_failed(self, message: str) -> None:
        settings.log(f"pass failed state={self.state}: {message}")
        self._job_id = None
        was_pass2 = self.state == PRINTING_PASS2
        self._set_state(DONE_ERROR if was_pass2 else READY)
        if self.dialog:
            self.dialog.show_phase(rundialog.FAILED, detail=message)
        else:
            messagebox.showerror("Printing", message)

    # ---- cancel -----------------------------------------------------
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

    # ---- dialog close / reset ------------------------------------
    def _close_dialog(self) -> None:
        if self.dialog:
            self.dialog.close()
            self.dialog = None
        if self.state in (DONE, DONE_ERROR):
            self.preview_text.set("Done — printed." if self.state == DONE
                                  else "Stopped — some sheets are one-sided.")
            self._set_state(self.state)
        else:
            self._set_state(READY)

    def _reset(self) -> None:
        self._cleanup_tmp()
        self.source_path = None
        self.plan = None
        self._job_id = None
        self._canceling = False
        self.file_label.config(text="No file chosen")
        self.preview_text.set("Choose a PDF.")
        self._set_thumb(None)
        self._set_state(READY)

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
        try:
            while True:
                kind, *rest = self._q.get_nowait()
                self._dispatch(kind, rest)
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def _dispatch(self, kind: str, rest: list) -> None:
        if kind == "plan":
            token, plan = rest
            if token == self._plan_token and self.state == READY:
                self._apply_plan(plan)
        elif kind == "thumb":
            token, png = rest
            if token == self._plan_token:
                self._set_thumb(png)
        elif kind == "plan_err":
            token, msg = rest
            if token == self._plan_token and self.state == READY:
                self.plan = None
                self.preview_text.set(msg)
                self._set_thumb(None)
                self._set_state(READY)
        elif kind == "submitted":
            _which, job_id = rest
            self._job_id = job_id
            self._gone_polls = 0
            self._detail("queued")
            self.after(_POLL_MS, self._poll_job)
        elif kind == "submit_err":
            which, exc = rest
            self._finish_pass_failed(f"Could not send the {which} pass: {exc}")
        elif kind == "cancel_err":
            (exc,) = rest
            self._canceling = False
            if self.dialog:
                self.dialog.enable_cancel()
                self.dialog.set_detail(f"Couldn't cancel — {exc}. Try again.")
        # "cancel_ok" needs no action — _poll_job sees the terminal state

    def _set_state(self, state: str) -> None:
        self.state = state
        inputs = "normal" if state == READY else "disabled"
        self.printer_menu.config(state=inputs)
        self.cover_menu.config(state=inputs)

        start_ok = state == READY and self.plan is not None and bool(self.printer.get())
        self.start_btn.config(state="normal" if start_ok else "disabled")
        (self.start_btn.grid if state == READY else self.start_btn.grid_remove)()
        (self.another_btn.grid if state in (DONE, DONE_ERROR)
         else self.another_btn.grid_remove)()

    # ============================================================= close
    def _cleanup_tmp(self) -> None:
        for f in self._tmpdir.glob("music-printer-*.pdf"):
            try:
                f.unlink()
            except OSError:
                pass

    def _on_close(self) -> None:
        if self._job_id and not self._canceling and self.state in _PRINTING:
            try:
                printing.cancel(self._job_id)
            except Exception:
                pass
        if self.dialog:
            try:
                self.dialog.close()
            except tk.TclError:
                pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
