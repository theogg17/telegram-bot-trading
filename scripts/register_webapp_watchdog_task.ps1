param(
  [string]$TaskName = "TradingBotWebAppWatchdog",
  [string]$WebAppTaskName = "TradingBotWebApp"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$WatchScript = Join-Path $Root "scripts\watch_webapp_health.ps1"

if (-not (Test-Path $WatchScript)) {
  throw "Missing watchdog script: $WatchScript"
}

$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$WatchScript`" -TaskName `"$WebAppTaskName`""

schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC MINUTE /MO 1 /RL HIGHEST /F | Out-Host

Write-Host "Registered watchdog task '$TaskName'."
Write-Host "It checks http://127.0.0.1:8000/healthz every minute and starts '$WebAppTaskName' if the WebApp is unreachable."
