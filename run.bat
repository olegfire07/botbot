@echo off
REM Windows launcher script for the Telegram bot
REM This script sets up the virtual environment and starts the bot

echo ========================================
echo    Telegram Bot Launcher (Windows)
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Creating...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment!
        echo Try running: python -m venv venv
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
    echo.
)

REM Verify venv activation script exists
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment appears corrupted!
    echo Please delete the 'venv' folder and run this script again.
    pause
    exit /b 1
)

REM Activate virtual environment and install dependencies
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
echo Checking dependencies...
venv\Scripts\pip.exe show python-telegram-bot >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies!
        pause
        exit /b 1
    )
    echo Dependencies installed successfully.
    echo.
)

REM Start the bot
echo Starting the bot...
echo Press Ctrl+C to stop the bot
echo.
venv\Scripts\python.exe run_modern_bot.py

REM If bot exits, pause to see any error messages
if errorlevel 1 (
    echo.
    echo Bot exited with an error!
    pause
)
