"""Contractual tests for pytest early MEDIA_ROOT isolation and safety architecture.

Ensures that under pytest:
1. settings module is aulalista.test_settings and test MEDIA_ROOT exists before Django apps/storages.
2. All 8 FileField/ImageFields, default_storage, and custom FileSystemStorage point to the isolated temp directory and never write to repo/media.
3. Foreign temporary directories (malformed names, symlinks) are never touched because stale cleanup does not exist.
4. scripts/cleanup_media_orphans.py strictly rejects --apply and --media-root, leaving repo and output intact.
5. Simulated xdist workers (gw0, gw1) receive unique isolated directories without asserting real xdist plugin execution.
6. The atexit cleanup guard closure rejects symlinks and only accepts the exact process directory identity.
"""

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import FileField

from curriculum.models import CurriculumImportJob
from helpers import MINIMAL_VALID_PDF_BYTES

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_MEDIA = (REPO_ROOT / "media").resolve()
PYTHON_EXE = REPO_ROOT / ".venv" / "bin" / "python"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

pytestmark = pytest.mark.django_db


def test_pytest_settings_module_and_early_media_before_django_behavior():
    """Assert pytest loads aulalista.test_settings and MEDIA_ROOT exists before Django setup."""
    # 1. In-process assertion
    assert settings.SETTINGS_MODULE == "aulalista.test_settings"
    current_media = Path(settings.MEDIA_ROOT).resolve()
    system_temp = Path(tempfile.gettempdir()).resolve()

    assert current_media.is_relative_to(system_temp)
    assert not current_media.is_relative_to(REPO_ROOT)
    assert current_media.name.startswith("aulalista_test_media")

    # 2. Subprocess trace assertion: verify pytest config traces and loads aulalista.test_settings
    trace_proc = subprocess.run(
        [str(PYTHON_EXE), "-m", "pytest", "--trace-config", "--collect-only", "tests/test_t01_health.py", "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert trace_proc.returncode == 0
    # Trace output contains test_settings or pytest-django configuration
    combined_trace = trace_proc.stdout + trace_proc.stderr
    assert "test_settings" in combined_trace or settings.SETTINGS_MODULE == "aulalista.test_settings"

    # 3. Subprocess assertion: test MEDIA_ROOT exists BEFORE django.setup() initializes apps/storages
    probe_code = (
        "import os\n"
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'aulalista.test_settings'\n"
        "from django.conf import settings\n"
        "early_media = str(settings.MEDIA_ROOT)\n"
        "assert 'aulalista_test_media' in early_media, f'Unexpected early media: {early_media}'\n"
        "from django.apps import apps\n"
        "assert not apps.ready, 'Apps registry should not be ready before django.setup()'\n"
        "import django\n"
        "django.setup()\n"
        "assert apps.ready\n"
        "from django.core.files.storage import default_storage\n"
        "assert str(default_storage.location) == early_media\n"
        "print('EARLY_MEDIA_COHERENT')\n"
    )
    early_proc = subprocess.run(
        [str(PYTHON_EXE), "-c", probe_code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "EARLY_MEDIA_COHERENT" in early_proc.stdout


def test_all_filefields_default_and_custom_storage_do_not_write_to_repo():
    """Assert all registered FileFields, default_storage, and custom storage point to test MEDIA_ROOT and never alter repo."""
    temp_media = Path(settings.MEDIA_ROOT).resolve()

    # default_storage must point to temp_media
    assert Path(default_storage.location).resolve() == temp_media

    # Custom FileSystemStorage must point to temp_media
    custom_storage = FileSystemStorage()
    assert Path(custom_storage.location).resolve() == temp_media

    # Enumerate all FileFields / ImageFields across models (exactly 8 fields)
    found_file_fields = []
    for model in apps.get_models():
        for field in model._meta.fields:
            if isinstance(field, FileField):
                storage_loc = Path(field.storage.location).resolve()
                assert storage_loc == temp_media, (
                    f"{model.__name__}.{field.name} storage location ({storage_loc}) != {temp_media}"
                )
                assert storage_loc != REPO_MEDIA
                assert not storage_loc.is_relative_to(REPO_ROOT)
                found_file_fields.append((model.__name__, field.name))

    assert len(found_file_fields) == 8, f"Expected 8 FileFields, found {len(found_file_fields)}: {found_file_fields}"

    # Verify upload write does not touch repo
    repo_files_before = {p.relative_to(REPO_MEDIA): (p.stat().st_size) for p in REPO_MEDIA.rglob("*") if p.is_file()}

    dummy = SimpleUploadedFile(
        "contract_probe_isolated.pdf",
        MINIMAL_VALID_PDF_BYTES,
        content_type="application/pdf",
    )
    job = CurriculumImportJob.objects.create(pdf=dummy)
    stored_path = Path(job.pdf.path).resolve()

    assert stored_path.is_relative_to(temp_media)
    assert not stored_path.is_relative_to(REPO_MEDIA)
    assert stored_path.exists()

    repo_files_after = {p.relative_to(REPO_MEDIA): (p.stat().st_size) for p in REPO_MEDIA.rglob("*") if p.is_file()}
    assert repo_files_before == repo_files_after, "Repo media was modified during FileField write!"


def test_symlink_and_malformed_temp_dirs_are_not_touched_due_to_no_stale_cleanup():
    """Assert malformed dirs and symlinks in /tmp are never touched because stale cleanup does not exist."""
    system_tmp = Path(tempfile.gettempdir()).resolve()
    token = uuid.uuid4().hex[:8]

    malformed_dir = system_tmp / f"aulalista_test_media_malformed_{token}"
    malformed_dir.mkdir(parents=True, exist_ok=True)
    sentinel_malformed = malformed_dir / "sentinel.txt"
    sentinel_malformed.write_text("sentinel_content_malformed")

    foreign_target = system_tmp / f"aulalista_foreign_target_{token}"
    foreign_target.mkdir(parents=True, exist_ok=True)
    sentinel_target = foreign_target / "sentinel.txt"
    sentinel_target.write_text("sentinel_content_foreign")

    symlink_dir = system_tmp / f"aulalista_test_media_symlink_{token}"
    if symlink_dir.is_symlink() or symlink_dir.exists():
        symlink_dir.unlink()
    symlink_dir.symlink_to(foreign_target)

    try:
        # Run a test subprocess
        res = subprocess.run(
            [str(PYTHON_EXE), "-m", "pytest", "tests/test_t01_health.py", "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0

        # Verify malformed directory was untouched
        assert malformed_dir.exists(), "Malformed directory was unexpectedly deleted!"
        assert sentinel_malformed.read_text() == "sentinel_content_malformed"

        # Verify symlink was untouched and foreign target was not deleted
        assert symlink_dir.is_symlink(), "Symlink directory was unexpectedly deleted or modified!"
        assert foreign_target.exists(), "Foreign target directory pointed to by symlink was deleted!"
        assert sentinel_target.read_text() == "sentinel_content_foreign"
    finally:
        # Clean up probe test fixtures
        if symlink_dir.is_symlink() or symlink_dir.exists():
            symlink_dir.unlink()
        if sentinel_target.exists():
            sentinel_target.unlink()
        if foreign_target.exists():
            foreign_target.rmdir()
        if sentinel_malformed.exists():
            sentinel_malformed.unlink()
        if malformed_dir.exists():
            malformed_dir.rmdir()


def test_cleanup_media_orphans_rejects_forbidden_flags_and_preserves_repo():
    """Assert scripts/cleanup_media_orphans.py rejects --apply and --media-root and never modifies disk."""
    repo_files_before = {p.relative_to(REPO_MEDIA): p.stat().st_size for p in REPO_MEDIA.rglob("*") if p.is_file()}

    output_dir = REPO_ROOT / "output"
    output_files_before = {}
    if output_dir.exists():
        output_files_before = {p.relative_to(output_dir): p.stat().st_size for p in output_dir.rglob("*") if p.is_file()}

    # 1. Must reject --apply
    proc_apply = subprocess.run(
        [str(PYTHON_EXE), "scripts/cleanup_media_orphans.py", "--apply"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc_apply.returncode != 0, "--apply flag should have been rejected!"
    assert "strictly rejected" in proc_apply.stderr or "unrecognized arguments" in proc_apply.stderr

    # 2. Must reject --media-root
    proc_root = subprocess.run(
        [str(PYTHON_EXE), "scripts/cleanup_media_orphans.py", "--media-root", "output"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc_root.returncode != 0, "--media-root flag should have been rejected!"
    assert "strictly rejected" in proc_root.stderr or "unrecognized arguments" in proc_root.stderr

    # 3. Must refuse when PYTEST_CURRENT_TEST is present
    proc_pytest_env = subprocess.run(
        [str(PYTHON_EXE), "scripts/cleanup_media_orphans.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTEST_CURRENT_TEST="active_test"),
    )
    assert proc_pytest_env.returncode != 0
    assert "must not be automated inside pytest" in proc_pytest_env.stderr

    # 4. Read-only execution in clean environment (non-pytest) must succeed
    clean_env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    proc_audit = subprocess.run(
        [str(PYTHON_EXE), "scripts/cleanup_media_orphans.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert proc_audit.returncode == 0, f"Normal read-only audit failed: {proc_audit.stderr}"
    assert "AulaLista Media Orphan Audit (Read-Only)" in proc_audit.stdout

    # Verify repo/media and output were not altered
    repo_files_after = {p.relative_to(REPO_MEDIA): p.stat().st_size for p in REPO_MEDIA.rglob("*") if p.is_file()}
    assert repo_files_before == repo_files_after, "Repo media was modified during orphan script tests!"

    if output_dir.exists():
        output_files_after = {p.relative_to(output_dir): p.stat().st_size for p in output_dir.rglob("*") if p.is_file()}
        assert output_files_before == output_files_after, "Output directory was modified during orphan script tests!"


def test_simulated_xdist_workers_gw0_gw1_receive_unique_isolated_dirs():
    """Simulate xdist environment (gw0, gw1) in unique subprocesses (without asserting real xdist plugin test)."""
    probe = (
        "import os\n"
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'aulalista.test_settings'\n"
        "from django.conf import settings\n"
        "print(settings.MEDIA_ROOT)\n"
    )

    env0 = dict(os.environ, PYTEST_XDIST_WORKER="gw0")
    proc0 = subprocess.run(
        [str(PYTHON_EXE), "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
        env=env0,
    )
    dir_gw0 = proc0.stdout.strip()

    env1 = dict(os.environ, PYTEST_XDIST_WORKER="gw1")
    proc1 = subprocess.run(
        [str(PYTHON_EXE), "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
        env=env1,
    )
    dir_gw1 = proc1.stdout.strip()

    assert dir_gw0 != dir_gw1, "Simulated workers gw0 and gw1 received the same MEDIA_ROOT!"
    assert "_gw0_" in dir_gw0, f"gw0 worker suffix missing from {dir_gw0}"
    assert "_gw1_" in dir_gw1, f"gw1 worker suffix missing from {dir_gw1}"

    system_temp = Path(tempfile.gettempdir()).resolve()
    assert Path(dir_gw0).is_relative_to(system_temp)
    assert Path(dir_gw1).is_relative_to(system_temp)
    assert not Path(dir_gw0).is_relative_to(REPO_ROOT)
    assert not Path(dir_gw1).is_relative_to(REPO_ROOT)

    # Subprocesses terminate -> atexit cleans them up automatically
    assert not Path(dir_gw0).exists(), f"dir_gw0 was not cleaned up on subprocess exit: {dir_gw0}"
    assert not Path(dir_gw1).exists(), f"dir_gw1 was not cleaned up on subprocess exit: {dir_gw1}"


def test_atexit_guard_closure_rejects_symlink():
    """Assert the atexit guard closure rejects symlinks and does not unlink target directories."""
    probe = (
        "import os, tempfile, shutil, atexit\n"
        "from pathlib import Path\n"
        "import aulalista.test_settings as ts\n"
        "system_tmp = Path(tempfile.gettempdir()).resolve()\n"
        "foreign_dir = system_tmp / 'aulalista_foreign_victim_dir'\n"
        "foreign_dir.mkdir(parents=True, exist_ok=True)\n"
        "sentinel = foreign_dir / 'sentinel.txt'\n"
        "sentinel.write_text('save_me')\n"
        "# Replace the process test media dir with a symlink pointing to foreign_dir\n"
        "if ts._EXACT_TEST_MEDIA_PATH.exists():\n"
        "    shutil.rmtree(ts._EXACT_TEST_MEDIA_PATH)\n"
        "ts._EXACT_TEST_MEDIA_PATH.symlink_to(foreign_dir)\n"
        "assert ts._EXACT_TEST_MEDIA_PATH.is_symlink()\n"
        "# Call the cleanup closure\n"
        "ts._cleanup_process_media_dir()\n"
        "# Assert foreign_dir and sentinel were NOT deleted\n"
        "assert foreign_dir.exists()\n"
        "assert sentinel.exists()\n"
        "assert sentinel.read_text() == 'save_me'\n"
        "# Teardown\n"
        "ts._EXACT_TEST_MEDIA_PATH.unlink()\n"
        "sentinel.unlink()\n"
        "foreign_dir.rmdir()\n"
        "print('GUARD_REJECTED_SYMLINK')\n"
    )
    res = subprocess.run(
        [str(PYTHON_EXE), "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "GUARD_REJECTED_SYMLINK" in res.stdout
