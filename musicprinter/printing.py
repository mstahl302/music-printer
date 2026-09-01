"""Send files to macOS printing (CUPS) and follow a job to completion.

Uses the always-present ``lp`` / ``lpstat`` command-line tools, so there is
no extra dependency and nothing special to bundle.

Job lifecycle as reported by :func:`job_status`:

    submitted --> "queued" --> "processing" --> "completed"
                     |                              ^
                     +--> printer paused/stopped ---+  (stays "queued")

    :func:`cancel` at any point --> "canceled";  a CUPS/printer failure
    --> "aborted".

``"gone"`` means CUPS no longer lists the job in either the active or the
completed queue (job history disabled, or it aged out) — usually it simply
finished, so the UI treats a short run of ``"gone"`` as done.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_TIMEOUT = 15


@dataclass(frozen=True)
class Printer:
    name: str
    is_default: bool


# --- discovery -----------------------------------------------------------

def list_printers() -> list[Printer]:
    """Every configured print destination, default first."""
    names = _run(["lpstat", "-e"]).split()
    default = default_printer()
    printers = [Printer(n, n == default) for n in names]
    printers.sort(key=lambda p: (not p.is_default, p.name.lower()))
    return printers


def default_printer() -> str | None:
    out = _run(["lpstat", "-d"])  # "system default destination: NAME"
    if "no system default" in out:
        return None
    m = re.search(r":\s*(\S+)", out)
    return m.group(1) if m else None


def printer_state(name: str) -> str:
    """``"idle"``, ``"printing"``, or ``"disabled"`` (paused / stopped)."""
    try:
        first = _run(["lpstat", "-p", name]).splitlines()[0].lower()
    except (subprocess.CalledProcessError, IndexError):
        return "disabled"
    if "disabled" in first:
        return "disabled"
    if "printing" in first:
        return "printing"
    return "idle"


# --- submitting --------------------------------------------------------

def submit(
    path,
    printer: str | None = None,
    *,
    copies: int = 1,
    two_sided: bool = False,
    fit_to_page: bool = False,
    title: str | None = None,
) -> str:
    """Queue ``path`` for printing and return the CUPS job id (``NAME-123``)."""
    cmd = ["lp"]
    if printer:
        cmd += ["-d", printer]
    if title:
        cmd += ["-t", title]
    if copies > 1:
        cmd += ["-n", str(copies)]
    if two_sided:
        cmd += ["-o", "sides=two-sided-long-edge"]
    if fit_to_page:
        cmd += ["-o", "fit-to-page"]
    cmd += [str(path)]

    out = _run(cmd)  # "request id is NAME-123 (1 file(s))"
    m = re.search(r"request id is (\S+)", out)
    if not m:
        raise RuntimeError(f"Could not read job id from lp output: {out!r}")
    return m.group(1)


# --- cancelling -------------------------------------------------------

def cancel(job_id: str) -> None:
    """Cancel a queued or printing job.

    No error if the job has already finished or vanished — only a job that
    is still active and refuses to cancel raises.
    """
    try:
        _run(["cancel", job_id])
    except subprocess.CalledProcessError as exc:
        if job_status(job_id) in ("queued", "processing"):
            raise RuntimeError(
                (exc.stderr or "").strip() or f"could not cancel {job_id}"
            ) from exc


# --- following the job ----------------------------------------------

def job_status(job_id: str) -> str:
    """One of ``"queued"``, ``"processing"``, ``"completed"``, ``"canceled"``,
    ``"aborted"``, ``"gone"``."""
    printer = job_id.rsplit("-", 1)[0]
    if job_id in _job_ids("not-completed"):
        block = _block_for(
            _safe_run(["lpstat", "-l", "-W", "not-completed", "-o", printer]).lower(),
            job_id.lower(),
        )
        if any(w in block for w in ("processing", "printing", "sending data")):
            return "processing"
        return "queued"
    if job_id in _job_ids("completed"):
        block = _block_for(
            _safe_run(["lpstat", "-l", "-W", "completed", "-o", printer]).lower(),
            job_id.lower(),
        )
        if "cancel" in block:
            return "canceled"
        if "abort" in block:
            return "aborted"
        return "completed"
    return "gone"


def _job_ids(which: str) -> set[str]:
    out = _safe_run(["lpstat", "-W", which, "-o"])
    return {ln.split()[0] for ln in out.splitlines() if ln.strip()}


def _block_for(detail: str, job_id: str) -> str:
    """The indented detail lines belonging to ``job_id`` in ``lpstat -l`` output."""
    lines = detail.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(job_id):
            block = [ln]
            for follow in lines[i + 1 :]:
                if follow[:1].isspace():
                    block.append(follow)
                else:
                    break
            return "\n".join(block)
    return ""


# --- process plumbing ---------------------------------------------------

def _run(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=_TIMEOUT
    ).stdout


def _safe_run(cmd: list[str]) -> str:
    try:
        return _run(cmd)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
