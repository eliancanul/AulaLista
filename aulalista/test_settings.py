"""Test settings for AulaLista with isolated MEDIA_ROOT.

Loaded directly via pytest.ini (DJANGO_SETTINGS_MODULE = aulalista.test_settings)
during the pytest-django initialization phase, before Django apps or storages
are configured.

Guarantees:
- Each test process and pytest-xdist worker receives a unique, isolated MEDIA_ROOT
  under the system temporary directory created with tempfile.mkdtemp.
- Exports AULALISTA_MEDIA_ROOT to os.environ for subprocess and in-process coherence.
- Registers an atexit cleanup handler with an exact local guard closure:
  - Rejects symlinks.
  - Only deletes the exact directory path created in this process.
  - No public cleanup API or exposure to stale directory attacks.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# 1. Import base settings
from .settings import *  # noqa: F401, F403

# 2. Worker/process differentiation for xdist or concurrent processes
_worker = os.environ.get("PYTEST_XDIST_WORKER", "").strip()
_worker_suffix = f"_{_worker}" if _worker else ""

# 3. Create unique test media root using mkdtemp
_raw_test_dir = tempfile.mkdtemp(prefix=f"aulalista_test_media{_worker_suffix}_")
_EXACT_TEST_MEDIA_PATH = Path(_raw_test_dir).resolve()

MEDIA_ROOT = str(_EXACT_TEST_MEDIA_PATH)
os.environ["AULALISTA_MEDIA_ROOT"] = MEDIA_ROOT


# 4. Register atexit cleanup with strict local guard closure (no public API)
def _cleanup_process_media_dir():
    try:
        # Strict local guard:
        # 1. Reject symlinks: must not be a symbolic link
        if os.path.islink(_EXACT_TEST_MEDIA_PATH):
            return
        # 2. Must exist and be a directory
        if not os.path.isdir(_EXACT_TEST_MEDIA_PATH):
            return
        # 3. Must match the exact identity and resolve to the exact created path
        resolved = _EXACT_TEST_MEDIA_PATH.resolve()
        if resolved != _EXACT_TEST_MEDIA_PATH:
            return
        # 4. Must strictly reside within system temp dir
        system_tmp = Path(tempfile.gettempdir()).resolve()
        if not resolved.is_relative_to(system_tmp):
            return
        # 5. Must not be inside repo root or match repo/media
        if resolved == BASE_DIR or resolved.is_relative_to(BASE_DIR):
            return
        # 6. Must have the required prefix
        if not resolved.name.startswith("aulalista_test_media"):
            return
        # 7. Path length sanity check (cannot be root or empty or system temp itself)
        if resolved in (system_tmp, Path("/"), Path.home()):
            return

        # Perform recursive removal of only this process's created directory
        shutil.rmtree(resolved, ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_process_media_dir)
