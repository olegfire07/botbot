$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$EnvFile = Join-Path $ScriptDir "sklad.env.ps1"

if (!(Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile. Copy sklad.env.ps1.example to sklad.env.ps1 and edit it."
}

. $EnvFile

Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --proxy-headers `
    --forwarded-allow-ips=127.0.0.1
