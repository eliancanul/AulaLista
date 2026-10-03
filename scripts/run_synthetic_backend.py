"""Run the declared synthetic backend scope; never label this the full suite."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.prepare_synthetic_ci import exclusion_reason


# Preserved tests with unavailable/private PDF assumptions, not deleted tests.
PRIVATE_MODULES = [
    "tests/test_v0_source_interpreter.py", "tests/test_v0_interpretation_flow.py",
    "tests/test_t18_task2_transition.py", "tests/test_t18_task3_retry.py",
    "tests/test_t18_task4_canonical_flow.py", "tests/test_t18_task5_verification.py",
    "tests/test_t18_task6_review_ui.py", "tests/test_t18_task7_approval.py",
    "tests/test_t_import_project_phases.py", "tests/test_t126_real_pipeline_smoke.py",
]
FROZEN_CORPUS_NODES = [
    "tests/test_sprint_luna.py::LunaFrozenCorpusTests",
    "tests/test_sprint_gemini.py::PublishedContractTests",
    "tests/test_sprint_gemini.py::ContractVersionTests::test_current_published_contract_has_explicit_outcome",
]


def validate_snapshot(root):
    manifest = root.parent / (root.name + "_manifest.json")
    if (root / ".git").exists() or not manifest.is_file():
        raise SystemExit("Run only inside the prepared synthetic snapshot")
    metadata = json.loads(manifest.read_text())
    if metadata.get("scope") != "synthetic acceptance only" or not metadata.get("materialized"):
        raise SystemExit("Invalid synthetic snapshot manifest")
    seen = set()
    for row in metadata["materialized"]:
        path = row["path"]
        target = root / path
        if (path in seen or exclusion_reason(path) or target.is_symlink()
                or not target.resolve().is_relative_to(root.resolve()) or not target.is_file()):
            raise SystemExit("Invalid or missing synthetic source entry")
        seen.add(path)
        if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
            raise SystemExit("Synthetic source changed after materialization")
    if any(exclusion_reason(path.relative_to(root).as_posix())
           for path in root.rglob("*") if path.is_file()):
        raise SystemExit("Excluded input found in synthetic snapshot; do not run tests")


def main():
    validate_snapshot(Path.cwd())
    if os.environ.get("AULALISTA_GEMINI_LIVE_ENABLED", "0") != "0":
        raise SystemExit("Synthetic CI requires live Gemini disabled")
    print("Synthetic backend scope. Private-input modules excluded:", *PRIVATE_MODULES,
          "Frozen corpus contracts excluded:", *FROZEN_CORPUS_NODES, sep="\n", flush=True)
    args = [sys.executable, "-m", "pytest", "-q", "-rs", "-m", "not browser", "tests"]
    args += ["--ignore=" + path for path in PRIVATE_MODULES]
    args += ["--deselect=" + node for node in FROZEN_CORPUS_NODES]
    result = subprocess.run(args)
    if result.returncode:
        return result.returncode
    # Keep the known self-contained normalization contract in its mixed module.
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs",
        "tests/test_t18_task5_verification.py::TestNormalization",
        "tests/s02_test_pdf_timeout.py"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
