import json
import sys
import subprocess
from pathlib import Path
from pypdf import PdfWriter
import hashlib
import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "shadow_import_curriculum.py"

def write_pdf(path, pages=3, *, width=612):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=792)
    with path.open("wb") as f:
        writer.write(f)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def invoke(*arguments, timeout=15):
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False,
    )


class TestCloseRawEmptyFails:
    def test_close_raw_empty_directory_fails(self, tmp_path):
        """close_raw on empty raw dir must fail, not pass with result_count=0."""
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "runs").mkdir()
        
        result = invoke("close-raw", "--raw-dir", str(raw))
        assert result.returncode != 0, (
            f"close-raw on empty dir should fail but returned 0. "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
        assert not (raw / "RAW-CLOSED.json").exists()


class TestPartitionIsolation:
    def test_same_sha256_across_splits_rejected(self, tmp_path):
        """Same PDF hash appearing in both train and test splits must be rejected."""
        source = tmp_path / "fixture.pdf"
        digest = write_pdf(source, pages=1)
        
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0.0",
            "documents": [
                {
                    "id": "TRAIN-01",
                    "path": str(source),
                    "sha256": digest,
                    "page_count": 1,
                    "split": "train",
                    "runner_eligible": True,
                },
                {
                    "id": "TEST-01",
                    "path": str(source),
                    "sha256": digest,
                    "page_count": 1,
                    "split": "test",
                    "runner_eligible": True,
                },
            ],
        }), encoding="utf-8")
        
        raw = tmp_path / "raw"
        result = invoke(
            "run-one", "--manifest", str(manifest_path),
            "--source-id", "TRAIN-01", "--adapter", "pypdf",
            "--raw-dir", str(raw), "--timeout-seconds", "2",
            "--replica", "1",
        )
        # Should reject due to partition isolation violation
        assert result.returncode != 0, (
            f"Same sha256 in train+test should be rejected but returned 0. "
            f"stderr={result.stderr[:300]}"
        )
