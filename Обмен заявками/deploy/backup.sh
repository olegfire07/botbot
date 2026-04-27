#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/sklad/sklad.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sklad}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

DB_PATH="${DATABASE_PATH:-/var/lib/sklad/sklad_requests.db}"
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="$BACKUP_DIR/sklad_requests_$STAMP.db"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

sqlite3 "$DB_PATH" ".backup '$TARGET'"
gzip -f "$TARGET"

find "$BACKUP_DIR" -name "sklad_requests_*.db.gz" -type f -mtime +30 -delete

echo "$TARGET.gz"
