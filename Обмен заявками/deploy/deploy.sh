#!/usr/bin/env bash
set -euo pipefail

DEPLOY_TARGET="${DEPLOY_TARGET:-root@195.208.3.92}"
APP_DIR="${APP_DIR:-/opt/sklad}"
SERVICE_NAME="${SERVICE_NAME:-sklad}"
HEALTH_URL="${HEALTH_URL:-https://fianit-antikvariat.ru/health}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="/tmp/sklad-deploy-$STAMP.tar.gz"
REMOTE_ARCHIVE="/tmp/sklad-deploy-$STAMP.tar.gz"

echo "== local tests =="
cd "$ROOT_DIR"
.venv/bin/python -m compileall -q app tests
.venv/bin/python -m pytest -q

echo "== build archive =="
COPYFILE_DISABLE=1 tar \
  --no-xattrs \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='._*' \
  --exclude='.DS_Store' \
  --exclude='exports' \
  --exclude='exports/*' \
  --exclude='*.xlsx' \
  --exclude='sklad_requests*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='*.zip' \
  -czf "$ARCHIVE" .
ls -lh "$ARCHIVE"

echo "== upload =="
scp "$ARCHIVE" "$DEPLOY_TARGET:$REMOTE_ARCHIVE"

echo "== remote deploy =="
ssh "$DEPLOY_TARGET" "APP_DIR='$APP_DIR' SERVICE_NAME='$SERVICE_NAME' REMOTE_ARCHIVE='$REMOTE_ARCHIVE' bash -s" <<'REMOTE'
set -euo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/var/backups/sklad"
mkdir -p "$BACKUP_DIR"

echo "== database backup =="
bash "$APP_DIR/deploy/backup.sh"

echo "== code backup =="
tar \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*/__pycache__' \
  --exclude='._*' \
  --exclude='exports' \
  --exclude='exports/*' \
  --exclude='*.xlsx' \
  --exclude='sklad_requests*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  -czf "$BACKUP_DIR/code_before_update_$STAMP.tar.gz" \
  -C "$APP_DIR" .
ls -lh "$BACKUP_DIR/code_before_update_$STAMP.tar.gz"

echo "== extract =="
tar -xzf "$REMOTE_ARCHIVE" -C "$APP_DIR"
find "$APP_DIR" -name '._*' -type f -delete
rm -f "$APP_DIR/replace_admin.py" "$APP_DIR/test_analytics.py" "$APP_DIR/test_sql.py"
chown -R sklad:sklad "$APP_DIR"

echo "== dependencies =="
cd "$APP_DIR"
sudo -u sklad .venv/bin/pip install -r requirements.txt

echo "== tests =="
sudo -u sklad .venv/bin/python -m compileall -q app tests
sudo -u sklad .venv/bin/python -m pytest -q

echo "== nginx =="
nginx -t
systemctl reload nginx

echo "== restart service =="
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl is-active "$SERVICE_NAME"

echo "== local health =="
curl -fsS http://127.0.0.1:8000/health
echo

rm -f "$REMOTE_ARCHIVE"
REMOTE

echo "== public health =="
curl -fsS "$HEALTH_URL"
echo

rm -f "$ARCHIVE"
echo "Deploy completed."
