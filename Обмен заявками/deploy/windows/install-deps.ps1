$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $ProjectRoot

if (!(Test-Path ".venv")) {
    py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

New-Item -ItemType Directory -Force -Path "C:\SkladData" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\SkladBackups" | Out-Null

Write-Host "Dependencies installed."
