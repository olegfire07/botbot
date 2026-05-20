@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.11 -c "import sys; sys.exit(0)" >nul 2>nul
  if %errorlevel%==0 set "PYTHON_EXE=py -3.11"
)
if "%PYTHON_EXE%"=="" (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
    if %errorlevel%==0 set "PYTHON_EXE=python"
  )
)
if "%PYTHON_EXE%"=="" (
  echo Python 3.11+ not found. Install it and retry.
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  %PYTHON_EXE% -m venv .venv
)

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing python.exe. Recreate .venv.
  exit /b 1
)

if not exist .venv\.deps_installed (
  echo Installing dependencies...
  .venv\Scripts\pip install -r requirements.txt
  if %errorlevel% neq 0 exit /b 1
  type nul > .venv\.deps_installed
)

if exist .bot.lock (
  set /p PID=<.bot.lock
  if not "%PID%"=="" (
    tasklist /FI "PID eq %PID%" | find "%PID%" >nul
    if %errorlevel%==0 (
      echo Bot already running (PID %PID%)
      exit /b 0
    ) else (
      del /f /q .bot.lock
    )
  )
)

start "" /min cmd /c ".venv\Scripts\python run_modern_bot.py > out.log 2>&1"
echo Started. Check out.log for status.
endlocal
