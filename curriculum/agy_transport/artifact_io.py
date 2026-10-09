"""Exclusive, atomic commits for bounded final-named artifacts; no external I/O."""
import json
import os
from pathlib import Path
import tempfile

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def commit(path, raw):
    path = Path(path)
    if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError('invalid_or_oversize_artifact')
    # Serialization is the caller's responsibility and precedes any open.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.pending-', dir=path.parent)
    temporary = Path(name)
    # On failure retain the explicitly pending bytes for forensic inspection.
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)  # Atomic no-overwrite; never os.replace/rename.
    dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
        temporary.unlink()
        os.fsync(dfd)
    finally:
        os.close(dfd)


def commit_json(path, value):
    commit(path, encoded(value))
