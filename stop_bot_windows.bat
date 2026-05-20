@echo off
setlocal
cd /d "%~dp0"

if not exist .bot.lock (
  echo No lockfile. Bot not running?
  exit /b 0
)

set /p PID=<.bot.lock
if "%PID%"=="" (
  echo Empty lockfile. Remove it and retry.
  exit /b 1
)

tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if %errorlevel%==0 (
  echo Stopping bot (PID %PID%)
  taskkill /PID %PID% /T >nul 2>&1
  timeout /t 2 >nul
) else (
  echo Process not found. Removing stale lockfile.
)

if exist .bot.lock del /f /q .bot.lock
echo Stopped.
endlocal
