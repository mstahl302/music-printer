#!/usr/bin/env python3
"""Music Printer — Tkinter front-end and two-pass state machine.

Pick a printer and a PDF, choose how to handle a vendor cover sheet, hit
Start. The app prints the EVEN pages, waits for the printer, asks you to
flip the stack, then prints the ODD pages onto the backs. See
docs/specification.md.
"""

from __future__ import annotations

import base64
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from musicprinter import jobs, printing, settings
from musicprinter.pdfio import PdfError

# UI label  ->  strip mode
COVER_MODES = {
    "Smart (detect)": "smart",
    "Always remove first page": "always",
    "Don't remove": "none",
}
MODE_TO_LABEL = {v: k for k, v in COVER_MODES.items()}

# state machine
READY = "ready"
PRINTING_PASS1 = "printing_pass1"
WAIT_FOR_FLIP = "wait_for_flip"
PRINTING_PASS2 = "printing_pass2"
PRINTING_SINGLE = "printing_single"
DONE = "done"
DONE_ERROR = "done_error"

_PRINTING = {PRINTING_PASS1, PRINTING_PASS2, PRINTING_SINGLE}


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
        self.printer = tk.StringVar(value=self.cfg["last_printer"])
        self.cover_label = tk.StringVar(value=MODE_TO_LABEL.get(self.cfg["strip_mode"], "Smart (detect)"))
        self.source_path: Path | None = None

        # derived
        self.plan: jobs.Plan | None = None
        self._plan_token = 0
        self._thumb_img: tk.PhotoImage | None = None

        # run state
        self.state = READY
        self._job_id: str | None = None
        self._gone_polls = 0
        self._canceling = False

        # display vars
        self.printer_warn = tk.StringVar(value="")
        self.preview_text = tk.StringVar(value="Choose a printer and a PDF.")
        self.status = tk.StringVar(value="")

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
        self.printer_menu = ttk.OptionMenu(frm, self.printer, "")
        self.printer_menu.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Label(frm, textvariable=self.printer_warn, foreground="#b00").grid(
            row=1, column=1, columnspan=2, sticky="w", padx=10)

        ttk.Button(frm, text="Choose PDF…", command=self._pick_file).grid(
            row=2, column=0, sticky="w", **pad)
        self.file_label = ttk.Label(frm, text="No file chosen", width=44, anchor="w")
        self.file_label.grid(row=2, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(frm, text="Cover sheet:").grid(row=3, column=0, sticky="w", **pad)
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

        # flip prompt (shown only in WAIT_FOR_FLIP)
        self.flip_frame = ttk.LabelFrame(frm, text="Flip the stack", padding=10)
        self.flip_frame.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(
            self.flip_frame, justify="left", wraplength=380,
            text=("Pass 1 is done. Take the printed stack out, flip it about the "
                  "SHORT edge, and put it back in the tray. Then click below."),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(self.flip_frame, text="Pages are flipped — print pass 2",
                   command=self._start_pass2).grid(row=1, column=0, pady=(8, 0))
        self.flip_frame.grid_remove()

        self.progress = ttk.Progressbar(frm, mode="indeterminate", length=380)
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", **pad)
        self.progress.grid_remove()
        ttk.Label(frm, textvariable=self.status, foreground="#555").grid(
            row=8, column=0, columnspan=3, sticky="w", padx=10)

        self.cancel_btn = ttk.Button(frm, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.grid(row=9, column=0, columnspan=3, **pad)

        self.another_btn = ttk.Button(frm, text="Print another", command=self._reset)
        self.another_btn.grid(row=10, column=0, columnspan=3, **pad)
        self.another_btn.grid_remove()

        self._set_state(READY)

    # ============================================================ printers
    def _load_printers(self) -> None:
        try:
            printers = printing.list_printers()
        except Exception as exc:
            self.preview_text.set(f"Could not list printers: {exc}")
            return
        menu = self.printer_menu["menu"]
        menu.delete(0, "end")
        for p in printers:
            label = f"{p.name}  (default)" if p.is_default else p.name
            menu.add_command(label=label, command=lambda n=p.name: self._choose_printer(n))
        names = [p.name for p in printers]
        if self.printer.get() not in names:
            default = next((p.name for p in printers if p.is_default), names[0] if names else "")
            self.printer.set(default)
        self._check_printer()

    def _choose_printer(self, name: str) -> None:
        self.printer.set(name)
        self.cfg["last_printer"] = name
        settings.save(self.cfg)
        self._check_printer()

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
        threading.Thread(target=self._plan_worker, args=(token, self.source_path,
                         self.cfg["strip_mode"], float(self.cfg["confidence_threshold"])),
                         daemon=True).start()

    def _plan_worker(self, token: int, path: Path, mode: str, threshold: float) -> None:
        try:
            plan = jobs.build_plan(path, mode, threshold=threshold)
            self._q.put(("plan", token, plan))
            png = None
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
        if self.plan is None or not self.printer.get():
            return
        self._check_printer()
        if self.printer_warn.get() and not messagebox.askyesno(
                "Printer paused", f"{self.printer_warn.get()}\n\nQueue the job anyway?"):
            return
        if self.plan.passes.single_pass:
            self._begin_pass("single", PRINTING_SINGLE, "Printing (single page)…")
        else:
            self._begin_pass("even", PRINTING_PASS1, "Printing pass 1 of 2 (even pages)…")

    def _start_pass2(self) -> None:
        self._begin_pass("odd", PRINTING_PASS2, "Printing pass 2 of 2 (odd pages)…")

    def _begin_pass(self, which: str, state: str, status: str) -> None:
        self._canceling = False
        self._job_id = None
        self._gone_polls = 0
        self._set_state(state)
        self.status.set(status)
        self.progress.grid()
        self.progress.start(12)
        # Read Tk vars here on the main thread; the worker must not touch Tk.
        threading.Thread(target=self._submit_worker,
                         args=(which, self.plan, self.printer.get()),
                         daemon=True).start()

    def _submit_worker(self, which: str, plan: "jobs.Plan", printer_name: str) -> None:
        try:
            pdf = jobs.build_pass_pdf(plan, which, self._tmpdir)
            title = f"{plan.source_path.name} — {which}"
            job_id = printing.submit(pdf, printer_name, title=title)
            settings.log(f"submit {which} job={job_id} file={pdf.name} "
                         f"pages={plan.n_effective} mode={plan.strip_mode}")
            self._q.put(("submitted", which, job_id))
        except Exception as exc:
            self._q.put(("submit_err", which, exc))

    def _poll_job(self) -> None:
        if self.state not in _PRINTING or not self._job_id:
            return
        try:
            st = printing.job_status(self._job_id)
        except Exception as exc:
            self._finish_pass_failed(f"Lost track of the job: {exc}")
            return
        delay = 400 if self._canceling else 700
        if st == "processing":
            self.status.set(f"Printing… — job {self._job_id}")
            self.after(delay, self._poll_job)
        elif st == "queued":
            self.status.set(f"Waiting in the printer queue — job {self._job_id}")
            self.after(400 if self._canceling else 1000, self._poll_job)
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
        self.progress.stop()
        self.progress.grid_remove()
        self._job_id = None
        if self.state == PRINTING_PASS1:
            self._set_state(WAIT_FOR_FLIP)
            self.status.set("Pass 1 finished. Flip the stack and continue.")
        else:  # PASS2 or SINGLE
            self._set_state(DONE)
            self.status.set("✅ Done — double-sided copy printed.")
            messagebox.showinfo("Done", "Double-sided copy printed.")

    def _finish_pass_canceled(self) -> None:
        settings.log(f"pass canceled state={self.state} job={self._job_id}")
        self.progress.stop()
        self.progress.grid_remove()
        self._job_id = None
        if self.state == PRINTING_PASS2:
            self._set_state(DONE_ERROR)
            self.status.set(f"🚫 Cancelled during pass 2 — job {self._job_id}.")
            messagebox.showwarning(
                "Cancelled",
                "Pass 2 was cancelled. Some sheets are printed on one side only.")
        else:
            self._set_state(READY)
            self.status.set("🚫 Cancelled.")

    def _finish_pass_failed(self, message: str) -> None:
        settings.log(f"pass failed state={self.state}: {message}")
        self.progress.stop()
        self.progress.grid_remove()
        self._job_id = None
        was_pass2 = self.state == PRINTING_PASS2
        self._set_state(DONE_ERROR if was_pass2 else READY)
        self.status.set(f"⚠️ {message}")
        messagebox.showerror("Printing", message)

    # ---- cancel -----------------------------------------------------
    def _cancel(self) -> None:
        if self.state == WAIT_FOR_FLIP:
            if messagebox.askyesno(
                    "Stop here?",
                    "Pass 1 sheets are already printed. Discard this file and start over?"):
                self._set_state(READY)
                self.status.set("Stopped after pass 1.")
            return
        if self.state in _PRINTING and self._job_id:
            self._canceling = True
            self.cancel_btn.config(state="disabled")
            self.status.set(f"Cancelling job {self._job_id}…")
            threading.Thread(target=self._cancel_worker, args=(self._job_id,),
                             daemon=True).start()

    def _cancel_worker(self, job_id: str) -> None:
        try:
            printing.cancel(job_id)
            self._q.put(("cancel_ok", job_id))
        except Exception as exc:
            self._q.put(("cancel_err", exc))

    # ---- reset ----------------------------------------------------
    def _reset(self) -> None:
        self._cleanup_tmp()
        self.source_path = None
        self.plan = None
        self._job_id = None
        self._canceling = False
        self.file_label.config(text="No file chosen")
        self.preview_text.set("Choose a PDF.")
        self._set_thumb(None)
        self.status.set("")
        self._set_state(READY)

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
            which, job_id = rest
            self._job_id = job_id
            self._gone_polls = 0
            self.status.set(f"Queued — job {job_id}")
            self.after(700, self._poll_job)
        elif kind == "submit_err":
            which, exc = rest
            self._finish_pass_failed(f"Could not send the {which} pass: {exc}")
        elif kind == "cancel_err":
            (exc,) = rest
            self._canceling = False
            self.cancel_btn.config(state="normal")
            self.status.set(f"Could not cancel: {exc}")
            messagebox.showerror("Cancel", str(exc))
        # "cancel_ok" needs no action — _poll_job sees the terminal state

    def _set_state(self, state: str) -> None:
        self.state = state
        printing_now = state in _PRINTING
        inputs = "disabled" if state != READY else "normal"
        self.printer_menu.config(state=inputs)
        self.cover_menu.config(state=inputs)

        start_ok = state == READY and self.plan is not None and bool(self.printer.get())
        self.start_btn.config(state="normal" if start_ok else "disabled")
        self.start_btn.grid() if state == READY else self.start_btn.grid_remove()

        self.flip_frame.grid() if state == WAIT_FOR_FLIP else self.flip_frame.grid_remove()

        cancel_ok = printing_now or state == WAIT_FOR_FLIP
        self.cancel_btn.config(state="normal" if cancel_ok else "disabled")

        self.another_btn.grid() if state in (DONE, DONE_ERROR) else self.another_btn.grid_remove()

    # ============================================================= close
    def _cleanup_tmp(self) -> None:
        for f in self._tmpdir.glob("music-printer-*.pdf"):
            try:
                f.unlink()
            except OSError:
                pass

    def _on_close(self) -> None:
        if self._job_id and self._canceling is False and self.state in _PRINTING:
            try:
                printing.cancel(self._job_id)
            except Exception:
                pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
