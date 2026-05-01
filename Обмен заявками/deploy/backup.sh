#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/sklad/sklad.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sklad}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

DB_PATH="${DATABASE_PATH:-/var/lib/sklad/sklad_requests.db}"
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="$BACKUP_DIR/sklad_requests_$STAMP.db"
GZ_TARGET="$TARGET.gz"

mkdir -p "$BACKUP_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

sqlite3 "$DB_PATH" ".backup '$TARGET'"

if [[ ! -s "$TARGET" ]]; then
  echo "Backup was not created or is empty: $TARGET" >&2
  exit 1
fi

if [[ "$(sqlite3 "$TARGET" 'PRAGMA integrity_check;')" != "ok" ]]; then
  echo "Backup integrity check failed: $TARGET" >&2
  exit 1
fi

gzip -f "$TARGET"
rm -f "$TARGET-shm" "$TARGET-wal"

if [[ ! -s "$GZ_TARGET" ]]; then
  echo "Compressed backup was not created or is empty: $GZ_TARGET" >&2
  exit 1
fi

gzip -t "$GZ_TARGET"
gunzip -c "$GZ_TARGET" > "$TMP_DIR/restore-test.db"

if [[ "$(sqlite3 "$TMP_DIR/restore-test.db" 'PRAGMA integrity_check;')" != "ok" ]]; then
  echo "Restore test failed: $GZ_TARGET" >&2
  exit 1
fi

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$GZ_TARGET" "$BACKUP_REMOTE"
  else
    scp "$GZ_TARGET" "$BACKUP_REMOTE"
  fi
fi

find "$BACKUP_DIR" -name "sklad_requests_*.db.gz" -type f -mtime +"$RETENTION_DAYS" -delete

echo "$GZ_TARGET"
