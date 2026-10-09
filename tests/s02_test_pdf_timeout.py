"""Process behavior on a tiny synthetic PDF; never a provider or load test."""

import json
import signal

import pytest

from curriculum.document_extraction import extract_document
from scripts.s02_pdf_timeout_probe import run_case, small_pdf


@pytest.mark.parametrize("mode,status,returncode,signals", [
    ("normal", "success", 0, []),
    ("slow", "timeout", -signal.SIGTERM, ["SIGTERM"]),
    ("ignore_term", "timeout", -signal.SIGKILL, ["SIGTERM", "SIGKILL"]),
    ("crash", "worker_error", 7, []),
])
def test_process_deadline_and_cleanup(mode, status, returncode, signals, tmp_path):
    evidence = run_case(mode, str(tmp_path))
    assert evidence["status"] == status
    assert evidence["returncode"] == returncode
    assert evidence["signals"] == signals
    assert evidence["reached_parser_boundary"]
    assert evidence["reaped"] and evidence["pid_absent"]
    assert evidence["temporary_directory_removed"]
    assert evidence["fixture_bytes"] < 2048
    assert evidence["elapsed_seconds"] < 5
    assert evidence["memory_measured"] is False
    if mode == "normal":
        payload = evidence["payload"]
        assert payload == json.loads(json.dumps(extract_document(small_pdf()).to_dict()))
        assert payload["status"] == "partial"
        assert payload["page_count"] == 2
        assert [page["status"] for page in payload["pages"]] == ["extracted", "empty"]
        assert payload["source_segments"][0]["text"] == "Actividad sintetica S02"
        assert payload["requires_review"] is True
        assert payload["pages"][1]["warnings"]
    else:
        assert evidence["payload"] is None
