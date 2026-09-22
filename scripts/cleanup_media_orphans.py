#!/usr/bin/env python3
"""Audit orphan files in media directory by cross-referencing database records.

Safety principles:
1. Strictly read-only audit: no files or directories are ever unlinked or deleted.
2. Production safety: refuses to run under active pytest execution.
3. Strict path containment: uses settings.MEDIA_ROOT exclusively; arbitrary --media-root
   and destructive --apply flags are strictly rejected.
4. Any cleanup in production requires a separate human-verified procedure with a DB snapshot.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aulalista.settings")


def get_db_referenced_media_paths(media_root: Path) -> set[Path]:
    """Collect all normalized file paths referenced by FileField or ImageField across models."""
    import django
    from django.apps import apps
    from django.db.models import FileField

    if not apps.ready:
        django.setup()

    referenced_paths: set[Path] = set()
    media_root_resolved = media_root.resolve()

    for model in apps.get_models():
        file_fields = [f.name for f in model._meta.fields if isinstance(f, FileField)]
        if not file_fields:
            continue

        for obj in model.objects.all().iterator():
            for field_name in file_fields:
                val = getattr(obj, field_name)
                if val and getattr(val, "name", None):
                    file_name = str(val.name).strip()
                    if not file_name:
                        continue
                    # Reject traversal / dangerous path components
                    if ".." in file_name or file_name.startswith(("/", "\\")):
                        continue
                    # Resolve path and verify containment
                    full_path = (media_root_resolved / file_name).resolve()
                    if full_path.is_relative_to(media_root_resolved):
                        referenced_paths.add(full_path)

    return referenced_paths


def scan_media_directory(media_root: Path) -> list[Path]:
    """Return all regular files present under media_root, rejecting symlinks."""
    media_root_resolved = media_root.resolve()
    if not media_root_resolved.exists() or not media_root_resolved.is_dir():
        return []

    files = []
    for p in sorted(media_root_resolved.rglob("*")):
        # Do not follow symlinks, reject non-files
        if p.is_file() and not p.is_symlink():
            resolved = p.resolve()
            if resolved.is_relative_to(media_root_resolved):
                files.append(resolved)
    return files


def find_orphan_files(media_root: Path) -> tuple[set[Path], list[Path]]:
    """Return (db_referenced_files, orphan_files)."""
    db_refs = get_db_referenced_media_paths(media_root)
    disk_files = scan_media_directory(media_root)

    orphans = [p for p in disk_files if p not in db_refs]
    return db_refs, orphans


def main():
    # Strict rejection of forbidden / dangerous flags
    for forbidden in ("--apply", "--media-root"):
        if forbidden in sys.argv:
            sys.stderr.write(
                f"ERROR: Flag '{forbidden}' is strictly rejected. "
                "This script is strictly a read-only audit tool using settings.MEDIA_ROOT exclusively.\n"
            )
            sys.exit(2)

    parser = argparse.ArgumentParser(
        description="Audit orphan files in media directory based on database references (read-only)."
    )
    parser.parse_args()

    # Safety guard: do not run in pytest
    if "PYTEST_CURRENT_TEST" in os.environ:
        sys.stderr.write("ERROR: orphan audit must not be automated inside pytest runs.\n")
        sys.exit(1)

    import django
    from django.conf import settings

    if not settings.configured:
        django.setup()

    # Exclusively use settings.MEDIA_ROOT
    media_root = Path(settings.MEDIA_ROOT).resolve()

    if not media_root.exists() or not media_root.is_dir():
        sys.stderr.write(f"ERROR: Media directory does not exist or is not a directory: {media_root}\n")
        sys.exit(1)

    if media_root.is_symlink():
        sys.stderr.write(f"ERROR: Media root cannot be a symlink: {media_root}\n")
        sys.exit(1)

    db_refs, orphans = find_orphan_files(media_root)

    total_orphan_bytes = sum(p.stat().st_size for p in orphans if p.exists())

    print("=" * 70)
    print("AulaLista Media Orphan Audit (Read-Only)")
    print("=" * 70)
    print(f"Media root:              {media_root}")
    print(f"Total files on disk:     {len(scan_media_directory(media_root))}")
    print(f"DB referenced files:     {len(db_refs)}")
    print(f"Orphan files found:      {len(orphans)}")
    print(f"Total orphan size:       {total_orphan_bytes:,} bytes ({total_orphan_bytes / 1024:.2f} KB)")
    print("-" * 70)

    for orphan in sorted(orphans):
        rel = orphan.relative_to(media_root)
        size = orphan.stat().st_size if orphan.exists() else 0
        print(f"  [ORPHAN] {rel} ({size:,} bytes)")

    if not orphans:
        print("\nNo orphan files found. Media storage is clean.")
    else:
        print("\n[READ-ONLY AUDIT MANIFEST] No files were deleted.")
        print("Production cleanup requires a separate, human-verified procedure with a DB snapshot.")


if __name__ == "__main__":
    main()
