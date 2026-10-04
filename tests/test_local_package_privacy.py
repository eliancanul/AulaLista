"""The local distributable must never copy operational or private input data.

Only invented files are archived. This test does not package the checkout.
"""
from pathlib import Path
import shutil
import subprocess
import tarfile


def test_local_package_excludes_private_runtime_and_inputs(tmp_path):
    project = tmp_path / "invented-project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "scripts" / "package_macos.sh"
    shutil.copyfile(source, scripts / "package_macos.sh")
    private_paths = [
        ".runtime/gemini/attempt/request.ndjson",
        ".runtime/gemini/STOP_UNKNOWN.json",
        "media/curriculum_imports/synthetic.pdf",
        "artifacts/synthetic-receipt.json",
        ".env",
        ".env.local",
        "output/pdf/synthetic-private.pdf",
        "docs/PLANEACIONES/synthetic-private.pdf",
        "docs/research/synthetic-private-manifest.json",
        "tests/fixtures/sprint_corpus/private-manifest.json",
        "prototypes/docente-skeleton/private-source.json",
        "custom-input/synthetic-private.pdf",
        "custom-input/synthetic-private.PDF",
        "frontend/node_modules/example/index.js",
        "db.sqlite3",
        "db.sqlite3-wal",
        "db.sqlite3-shm",
        "db.sqlite3-journal",
    ]
    public_paths = [
        "manage.py",
        "curriculum/teacher_review.py",
        "templates/curriculum/tutor_teacher_review.html",
        "static/curriculum/teacher-review.js",
        "static/curriculum/teacher-review.css",
        "docs/teacher-review.md",
    ]
    for name in private_paths + public_paths:
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("synthetic-only fixture\n", encoding="utf-8")
    output = tmp_path / "package-output"
    subprocess.run(["sh", str(scripts / "package_macos.sh"), str(output)],
                   cwd=project, check=True, capture_output=True, text=True)
    with tarfile.open(output / "aulalista-local.tar.gz", "r:gz") as archive:
        members = set(archive.getnames())
    leaked = [name for name in private_paths if f"{project.name}/{name}" in members]
    assert leaked == [], f"Private operational/input files included: {leaked}"
    for name in public_paths:
        assert f"{project.name}/{name}" in members
