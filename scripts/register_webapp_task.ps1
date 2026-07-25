param(
  [string]$TaskName = "TradingBotWebApp",
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $Root "scripts\start_webapp.ps1"

if (-not (Test-Path $StartScript)) {
  throw "Missing start script: $StartScript"
}

$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""

schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC ONLOGON /RL HIGHEST /F | Out-Host

if ($RunNow) {
  schtasks.exe /Run /TN $TaskName | Out-Host
}

Write-Host "Registered task '$TaskName'."
Write-Host "It starts the WebApp when this Windows user logs on."
