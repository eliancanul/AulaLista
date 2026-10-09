"""The local distributable must never copy operational or private input data.

Only invented files are archived. This test does not package the checkout.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tarfile

import pytest


@pytest.mark.parametrize("project_name", ["invented-project", "fixture[abc]", "fixture*?name", "-fixture", "back\\slash", "^fixture"])
def test_local_package_excludes_private_runtime_and_inputs(tmp_path, project_name):
    project = tmp_path / project_name
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
        "docs/evidence/t12-network.mmd",
        "docs/evidence/public.json",
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


@pytest.mark.parametrize("destination", ["default", "root", "nested", "external"])
def test_package_never_archives_its_output_or_temporary_files(tmp_path, destination):
    project = tmp_path / "synthetic project á"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts/package_macos.sh",
                    scripts / "package_macos.sh")
    (project / "manage.py").write_text("# invented public input\n")
    output = {"default": project / "dist", "root": project,
              "nested": project / "custom [output] ? á", "external": tmp_path / "external output"}[destination]
    output.mkdir(exist_ok=True)
    # Old outputs/temporaries must neither be copied nor read as source inputs.
    archive_path = output / "aulalista-local.tar.gz"
    archive_path.write_bytes(b"old distributable")
    stale_temp = output / ".aulalista-local.stale"
    stale_temp.write_text("preserve this old file, do not archive it")
    args = ["sh", str(scripts / "package_macos.sh")]
    if destination != "default":
        args.append(str(output))
    for _ in range(2):
        result = subprocess.run(args, cwd=tmp_path, check=True, capture_output=True, text=True)
        assert result.stdout.strip() == str(archive_path)
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
            assert f"{project.name}/manage.py" in names
            assert not any(Path(name).name == "aulalista-local.tar.gz" or
                           Path(name).name.startswith(".aulalista-local.") for name in names)
        assert list(output.glob(".aulalista-local.*")) == [stale_temp]
        assert stale_temp.read_text() == "preserve this old file, do not archive it"
        assert (project / "manage.py").read_text() == "# invented public input\n"


def test_failed_package_keeps_previous_archive_and_cleans_only_its_temp(tmp_path):
    project = tmp_path / "synthetic-project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts/package_macos.sh",
                    scripts / "package_macos.sh")
    output = project / "custom output"
    output.mkdir()
    archive = output / "aulalista-local.tar.gz"
    archive.write_bytes(b"previous complete archive")
    source = project / "manage.py"
    source.write_bytes(b"source preserved")
    old_temp = output / ".aulalista-local.unrelated"
    old_temp.write_bytes(b"older temporary preserved")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_tar = fake_bin / "tar"
    fake_tar.write_text("#!/bin/sh\nexit 73\n")
    fake_tar.chmod(0o700)
    result = subprocess.run(["sh", str(scripts / "package_macos.sh"), str(output)],
                            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
                            capture_output=True, text=True)
    assert result.returncode == 73
    assert archive.read_bytes() == b"previous complete archive"
    assert source.read_bytes() == b"source preserved"
    assert old_temp.read_bytes() == b"older temporary preserved"
    assert list(output.glob(".aulalista-local.*")) == [old_temp]
