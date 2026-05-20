#!/bin/zsh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "python3.12 not found. Install Python 3.12 and retry."
  exit 1
fi

PY_OK=$(python3.12 - <<'PY'
import sys
print("yes" if sys.version_info[:2] == (3, 12) else "no")
PY
)
if [ "$PY_OK" != "yes" ]; then
  echo "Python 3.12 required. Please install and retry."
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  VENV_OK=$(".venv/bin/python" - <<'PY'
import sys
print("yes" if sys.version_info[:2] == (3, 12) else "no")
PY
  )
  if [ "$VENV_OK" != "yes" ]; then
    echo "Recreating virtual environment for Python 3.12..."
    rm -rf .venv
  fi
fi

if [ ! -d ".venv" ] || [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  if ! python3.12 -m venv .venv; then
    echo "Retrying virtual environment creation with --copies..."
    rm -rf .venv
    python3.12 -m venv --copies .venv
  fi
fi

VENV_PY=".venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "Virtual environment creation failed. Check Python installation."
  exit 1
fi

if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ]; then
  echo "Installing dependencies..."
  "$VENV_PY" -m pip install -r requirements.txt
  touch .venv/.deps_installed
fi

if [ -f .bot.lock ]; then
  PID=$(cat .bot.lock 2>/dev/null || true)
  if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
    echo "Bot already running (PID $PID)"
    exit 0
  fi
  echo "Removing stale lockfile"
  rm -f .bot.lock
fi

nohup "$VENV_PY" "$DIR/run_modern_bot.py" > out.log 2>&1 &
BG_PID=$!
echo "$BG_PID" > bot.pid
sleep 1

if [ -f .bot.lock ]; then
  echo "Started (PID $(cat .bot.lock))"
else
  echo "Started (PID $BG_PID). Check out.log"
fi
