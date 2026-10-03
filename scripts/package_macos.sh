#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR=${1:-"$ROOT/dist"}
ARCHIVE="$OUTPUT_DIR/aulalista-local.tar.gz"
PROJECT_NAME=$(basename "$ROOT")
PARENT_DIR=$(dirname "$ROOT")

mkdir -p "$OUTPUT_DIR"
rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" \
  -C "$PARENT_DIR" \
  --exclude="$PROJECT_NAME/.git" \
  --exclude="$PROJECT_NAME/.venv" \
  --exclude="$PROJECT_NAME/.pytest_cache" \
  --exclude="$PROJECT_NAME/__pycache__" \
  --exclude="$PROJECT_NAME/*/__pycache__" \
  --exclude="$PROJECT_NAME/db.sqlite3" \
  --exclude="$PROJECT_NAME/db.sqlite3-wal" \
  --exclude="$PROJECT_NAME/db.sqlite3-shm" \
  --exclude="$PROJECT_NAME/db.sqlite3-journal" \
  --exclude="$PROJECT_NAME/staticfiles" \
  --exclude="$PROJECT_NAME/.runtime" \
  --exclude="$PROJECT_NAME/media" \
  --exclude="$PROJECT_NAME/artifacts" \
  --exclude="$PROJECT_NAME/.env" \
  --exclude="$PROJECT_NAME/.env.*" \
  --exclude="$PROJECT_NAME/output" \
  --exclude="$PROJECT_NAME/outputs" \
  --exclude="$PROJECT_NAME/evidence" \
  --exclude="$PROJECT_NAME/docs/PLANEACIONES" \
  --exclude="$PROJECT_NAME/docs/research" \
  --exclude="$PROJECT_NAME/dist" \
  "$PROJECT_NAME"

printf '%s\n' "$ARCHIVE"
