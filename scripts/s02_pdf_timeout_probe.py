"""Bounded POSIX experiment, not a production upload runner or sandbox."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


MODES = ("normal", "slow", "ignore_term", "crash")
DEADLINE_SECONDS = 3.0
TERM_GRACE_SECONDS = 0.2
REAP_SECONDS = 1.0
ROOT = Path(__file__).resolve().parents[1]


def small_pdf() -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Actividad sintetica S02) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def worker(mode: str, directory: Path) -> None:
    from curriculum import document_extraction
    from unittest.mock import patch

    if mode == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    reader = document_extraction.PdfReader

    def controlled_reader(*args, **kwargs):
        (directory / "ready").write_text("parser_boundary", encoding="utf-8")
        if mode == "crash":
            os._exit(7)
        if mode in ("slow", "ignore_term"):
            time.sleep(10)  # Deliberate bounded fixture delay; no expensive PDF.
        return reader(*args, **kwargs)

    with patch.object(document_extraction, "PdfReader", controlled_reader):
        result = document_extraction.extract_document((directory / "input.pdf").read_bytes())
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(result.to_dict()), encoding="utf-8")
    temporary.replace(directory / "result.json")


def signal_group(process: subprocess.Popen, signum: int) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def run_case(mode: str, scratch_root: str) -> dict:
    if os.name != "posix" or mode not in MODES:
        raise ValueError("El diagnóstico requiere POSIX y un caso sintético conocido.")
    content = small_pdf()
    with tempfile.TemporaryDirectory(prefix="s02-timeout-", dir=scratch_root) as temporary:
        directory = Path(temporary)
        (directory / "input.pdf").write_bytes(content)
        started = time.monotonic()
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.s02_pdf_timeout_probe", "--worker", mode, temporary],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        timed_out = False
        signals = []
        try:
            try:
                process.wait(timeout=max(0, DEADLINE_SECONDS - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
                signals.append("SIGTERM")
                signal_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=TERM_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    signals.append("SIGKILL")
                    signal_group(process, signal.SIGKILL)
                    process.wait(timeout=REAP_SECONDS)
        finally:
            if process.poll() is None:
                signal_group(process, signal.SIGKILL)
                process.wait(timeout=REAP_SECONDS)
        elapsed = time.monotonic() - started
        try:
            os.kill(process.pid, 0)
            pid_absent = False
        except ProcessLookupError:
            pid_absent = True
        status = "timeout" if timed_out else "success" if process.returncode == 0 else "worker_error"
        payload = None
        if status == "success":
            payload = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        evidence = {
            "mode": mode, "status": status, "fixture_bytes": len(content),
            "deadline_seconds": DEADLINE_SECONDS, "term_grace_seconds": TERM_GRACE_SECONDS,
            "reap_seconds": REAP_SECONDS, "elapsed_seconds": round(elapsed, 4),
            "signals": signals, "returncode": process.returncode,
            "reaped": process.returncode is not None, "pid_absent": pid_absent,
            "reached_parser_boundary": (directory / "ready").exists(),
            "payload": payload, "memory_measured": False,
        }
    evidence["temporary_directory_removed"] = not directory.exists()
    return evidence


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker" and sys.argv[2] in MODES:
        worker(sys.argv[2], Path(sys.argv[3]))
    elif len(sys.argv) == 1:
        scratch = os.environ.get("AULALISTA_SCRATCH_DIR", tempfile.gettempdir())
        print(json.dumps([run_case(mode, scratch) for mode in MODES], ensure_ascii=False, indent=2))
    else:
        raise SystemExit("Uso: python -m scripts.s02_pdf_timeout_probe")
