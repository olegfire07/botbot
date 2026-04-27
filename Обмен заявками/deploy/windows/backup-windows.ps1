$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$EnvFile = Join-Path $ScriptDir "sklad.env.ps1"

if (Test-Path $EnvFile) {
    . $EnvFile
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DbPath = if ($env:DATABASE_PATH) { $env:DATABASE_PATH } else { Join-Path $ProjectRoot "sklad_requests.db" }
$BackupDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { "C:\SkladBackups" }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$Code = @"
import gzip
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

db_path = Path(os.environ.get("DATABASE_PATH", r"$DbPath"))
backup_dir = Path(os.environ.get("BACKUP_DIR", r"$BackupDir"))
backup_dir.mkdir(parents=True, exist_ok=True)

if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
raw_target = backup_dir / f"sklad_requests_{stamp}.db"
gz_target = raw_target.with_suffix(".db.gz")

source = sqlite3.connect(str(db_path))
target = sqlite3.connect(str(raw_target))
try:
    source.backup(target)
finally:
    target.close()
    source.close()

with raw_target.open("rb") as src, gzip.open(gz_target, "wb") as dst:
    shutil.copyfileobj(src, dst)
raw_target.unlink()

cutoff = datetime.now() - timedelta(days=30)
for old_backup in backup_dir.glob("sklad_requests_*.db.gz"):
    if datetime.fromtimestamp(old_backup.stat().st_mtime) < cutoff:
        old_backup.unlink()

print(gz_target)
"@

& $Python -c $Code
