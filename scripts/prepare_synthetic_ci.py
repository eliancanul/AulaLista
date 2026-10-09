"""Export an exact code snapshot without private source inputs, before testing.

Reads Git metadata first and never opens excluded blobs. This is a synthetic
acceptance boundary, not a private-corpus evaluation or a distribution archive.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


PRIVATE_PREFIXES = (
    "output/", "outputs/", "media/", "artifacts/", "evidence/", ".runtime/",
    "docs/PLANEACIONES/", "docs/research/", "tests/fixtures/sprint_corpus/",
    "prototypes/docente-skeleton/",
)
# These historical modules require the excluded frozen corpus/private fixtures.
PRIVATE_FILES = {
    "scripts/sprint_eval/corpus.py",
    "tests/test_t_implicit_finality_and_phases.py",
    "tests/test_t_implicit_finality_persistence.py",
}


def exclusion_reason(path):
    if path.startswith(PRIVATE_PREFIXES) or path in PRIVATE_FILES:
        return "private_or_frozen_input_scope"
    if path.lower().endswith((".pdf", ".sqlite3", ".db")):
        return "source_or_database_input"
    if any(part == ".env" or part.startswith(".env.") for part in Path(path).parts):
        return "environment_file"
    return None


def prepare(repo, destination):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    head = git("rev-parse", "HEAD").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"head": head, "tree": tree, "scope": "synthetic acceptance only",
                "materialized": [], "excluded_counts": {}}
    for entry in git("ls-tree", "-rz", head).split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        path = raw_path.decode()
        reason = exclusion_reason(path)
        if reason:
            counts = manifest["excluded_counts"]
            counts[reason] = counts.get(reason, 0) + 1
            continue  # Do not read, hash, print or export excluded source content.
        if mode not in ("100644", "100755") or kind != "blob":
            raise RuntimeError("Unexpected nonregular tracked entry in synthetic scope")
        target = destination / path
        if not target.resolve().is_relative_to(destination.resolve()):
            raise RuntimeError("Invalid tracked path")
        # Unexpected missing code is a failure, never an implicit test exclusion.
        data = git("cat-file", "blob", blob)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        manifest["materialized"].append({"path": path, "git_blob": blob,
                                        "sha256": hashlib.sha256(data).hexdigest()})
    (destination.parent / (destination.name + "_manifest.json")).write_text(
        json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"head": head, "tree": tree, "scope": manifest["scope"],
                      "code_files": len(manifest["materialized"]),
                      "excluded_counts": manifest["excluded_counts"]}))
    return manifest


if __name__ == "__main__":
    prepare(Path(__file__).resolve().parents[1], Path(sys.argv[1]).resolve())
