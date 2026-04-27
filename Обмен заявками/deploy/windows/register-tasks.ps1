$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$StartScript = Join-Path $ScriptDir "start-sklad.ps1"
$BackupScript = Join-Path $ScriptDir "backup-windows.ps1"

$AppAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$AppTrigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask `
    -TaskName "Sklad App" `
    -Action $AppAction `
    -Trigger $AppTrigger `
    -Description "Starts Fianit Sklad FastAPI app" `
    -RunLevel Highest `
    -Force

$BackupAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$BackupScript`""
$BackupTrigger = New-ScheduledTaskTrigger -Daily -At 2:15am
Register-ScheduledTask `
    -TaskName "Sklad Backup" `
    -Action $BackupAction `
    -Trigger $BackupTrigger `
    -Description "Backs up Fianit Sklad SQLite database" `
    -RunLevel Highest `
    -Force

$CaddyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -Command `"caddy run --config C:\SkladApp\deploy\windows\Caddyfile`""
$CaddyTrigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask `
    -TaskName "Sklad Caddy" `
    -Action $CaddyAction `
    -Trigger $CaddyTrigger `
    -Description "Starts Caddy reverse proxy for Sklad" `
    -RunLevel Highest `
    -Force

Write-Host "Registered tasks: Sklad App, Sklad Backup, Sklad Caddy"
