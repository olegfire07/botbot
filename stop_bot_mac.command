#!/bin/zsh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PID=""
if [ -f .bot.lock ]; then
  PID=$(cat .bot.lock 2>/dev/null || true)
fi

if [ -z "$PID" ] && [ -f bot.pid ]; then
  PID=$(cat bot.pid 2>/dev/null || true)
fi

if [ -z "$PID" ]; then
  PIDS=($(pgrep -f "$DIR/run_modern_bot.py" 2>/dev/null || true))
  if [ ${#PIDS[@]} -eq 0 ]; then
    PIDS=($(pgrep -f "run_modern_bot.py" 2>/dev/null || true))
  fi

  if [ ${#PIDS[@]} -eq 0 ]; then
    echo "No lockfile or pidfile, and no running process found."
    exit 0
  fi

  if [ ${#PIDS[@]} -gt 1 ]; then
    echo "Multiple bot processes found:"
    ps -p ${PIDS[@]} -o pid,command
    echo "Stop them manually or update bot.pid."
    exit 1
  fi
  PID="${PIDS[1]}"
fi

if [ -z "$PID" ]; then
  echo "No PID found."
  exit 1
fi

if ps -p "$PID" >/dev/null 2>&1; then
  echo "Stopping bot (PID $PID)"
  kill -INT "$PID" || true
  sleep 2
  if ps -p "$PID" >/dev/null 2>&1; then
    kill "$PID" || true
    sleep 2
  fi
else
  echo "Process not found. Removing stale lockfile/pidfile."
fi

if ps -p "$PID" >/dev/null 2>&1; then
  echo "Bot is still running. Try again or stop manually."
  exit 1
fi

rm -f .bot.lock bot.pid
echo "Stopped"
