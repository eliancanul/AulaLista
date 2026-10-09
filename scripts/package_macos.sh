#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR=${1:-"$ROOT/dist"}
PROJECT_NAME=$(basename "$ROOT")
# Quote wildcard characters in the literal top-level name for tar patterns.
EXCLUDE_ROOT=$(printf '%s\n' "$PROJECT_NAME" | sed 's/[][\\*?^]/\\&/g')
PARENT_DIR=$(dirname "$ROOT")

mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
ARCHIVE="$OUTPUT_DIR/aulalista-local.tar.gz"
# Write beside the destination, then replace only after tar succeeds. A failed
# build must leave the prior distributable and all source inputs untouched.
TEMP_ARCHIVE=$(mktemp "$OUTPUT_DIR/.aulalista-local.XXXXXX")
trap 'rm -f "$TEMP_ARCHIVE"' 0
trap 'exit 1' HUP INT TERM
# Keep private exclusions anchored to the escaped top-level name. Public
# docs/evidence must not be confused with the private root evidence directory.
tar -czf "$TEMP_ARCHIVE" \
  -C "$PARENT_DIR" \
  --exclude="$EXCLUDE_ROOT/.git" \
  --exclude="$EXCLUDE_ROOT/.venv" \
  --exclude="$EXCLUDE_ROOT/.pytest_cache" \
  --exclude="$EXCLUDE_ROOT/__pycache__" \
  --exclude="$EXCLUDE_ROOT/*/__pycache__" \
  --exclude="$EXCLUDE_ROOT/db.sqlite3" \
  --exclude="$EXCLUDE_ROOT/db.sqlite3-wal" \
  --exclude="$EXCLUDE_ROOT/db.sqlite3-shm" \
  --exclude="$EXCLUDE_ROOT/db.sqlite3-journal" \
  --exclude="$EXCLUDE_ROOT/staticfiles" \
  --exclude="$EXCLUDE_ROOT/.runtime" \
  --exclude="$EXCLUDE_ROOT/media" \
  --exclude="$EXCLUDE_ROOT/artifacts" \
  --exclude="$EXCLUDE_ROOT/.env" \
  --exclude="$EXCLUDE_ROOT/.env.*" \
  --exclude="$EXCLUDE_ROOT/output" \
  --exclude="$EXCLUDE_ROOT/outputs" \
  --exclude="$EXCLUDE_ROOT/evidence" \
  --exclude="$EXCLUDE_ROOT/docs/PLANEACIONES" \
  --exclude="$EXCLUDE_ROOT/docs/research" \
  --exclude="$EXCLUDE_ROOT/tests/fixtures/sprint_corpus" \
  --exclude="$EXCLUDE_ROOT/prototypes/docente-skeleton" \
  --exclude="$EXCLUDE_ROOT/frontend/node_modules" \
  --exclude="*.[pP][dD][fF]" \
  --exclude="$EXCLUDE_ROOT/dist" \
  --exclude="*/aulalista-local.tar.gz" \
  --exclude="*/.aulalista-local.*" \
  -- "$PROJECT_NAME"

mv -f "$TEMP_ARCHIVE" "$ARCHIVE"
printf '%s\n' "$ARCHIVE"
