"""The CI exporter must not read or publish private inputs from the checkout."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.prepare_synthetic_ci import exclusion_reason, prepare


@pytest.mark.parametrize("name", ["output/source.pdf", "other/source.PDF", ".env", ".env.local",
    "media/file.txt", "docs/research/notes.md", "docs/PLANEACIONES/input.txt",
    "tests/fixtures/sprint_corpus/cases.json", ".runtime/receipt.json", "db.sqlite3"])
def test_private_inputs_have_explicit_exclusion(name):
    assert exclusion_reason(name)


def test_exact_synthetic_export_preserves_code_without_reading_private_blobs(tmp_path, monkeypatch):
    repo = tmp_path / "invented-repository"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    git("init", "-q")
    (repo / "code.py").write_text("print('synthetic')\n")
    for name in ("input.pdf", ".env", "output/private.txt"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PRIVATE_SENTINEL_NOT_A_REAL_INPUT")
    git("add", ".")
    tree = git("write-tree").decode().strip()
    head = git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@invalid.test",
               "commit-tree", tree, "-m", "Synthetic exporter fixture").decode().strip()
    git("update-ref", "HEAD", head)
    code_blob = git("rev-parse", "HEAD:code.py").decode().strip()
    original = subprocess.check_output
    reads = []
    def guarded(argv, **kwargs):
        if "cat-file" in argv:
            reads.append(argv[-1])
            assert argv[-1] == code_blob, "Exporter attempted to read an excluded input blob"
        return original(argv, **kwargs)
    monkeypatch.setattr(subprocess, "check_output", guarded)
    snapshot = tmp_path / "snapshot"
    manifest = prepare(repo, snapshot)
    assert reads == [code_blob]
    assert manifest["head"] == head and manifest["tree"] == tree
    assert [row["path"] for row in manifest["materialized"]] == ["code.py"]
    assert (snapshot / "code.py").read_text() == "print('synthetic')\n"
    assert sum(manifest["excluded_counts"].values()) == 3
    assert set(p.name for p in snapshot.iterdir()) == {"code.py"}
    receipt = json.loads((tmp_path / "snapshot_manifest.json").read_text())
    assert "PRIVATE_SENTINEL" not in json.dumps(receipt)
    assert hashlib.sha256((snapshot / "code.py").read_bytes()).hexdigest() == receipt["materialized"][0]["sha256"]

    from scripts.run_synthetic_backend import validate_snapshot
    validate_snapshot(snapshot)
    (snapshot / "code.py").write_text("changed after freeze")
    with pytest.raises(SystemExit, match="changed after materialization"):
        validate_snapshot(snapshot)
