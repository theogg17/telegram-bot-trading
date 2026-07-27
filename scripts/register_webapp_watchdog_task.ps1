param(
  [string]$TaskName = "TradingBotWebAppWatchdog",
  [string]$WebAppTaskName = "TradingBotWebApp",
  [string]$Mt5TaskName = "TradingBotMT5",
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$WatchScript = Join-Path $Root "scripts\watch_webapp_health.ps1"

if (-not (Test-Path -LiteralPath $WatchScript -PathType Leaf)) {
  throw "Missing watchdog script: $WatchScript"
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$PrincipalObject = New-Object Security.Principal.WindowsPrincipal($Identity)
$AdminRole = [Security.Principal.WindowsBuiltInRole]::Administrator
if (-not $PrincipalObject.IsInRole($AdminRole)) {
  throw "Run this script from PowerShell as Administrator."
}

$UserId = $Identity.Name
$Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$WatchScript`" -TaskName `"$WebAppTaskName`" -Mt5TaskName `"$Mt5TaskName`""
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arguments -WorkingDirectory ([string]$Root)
$RepeatTrigger = New-ScheduledTaskTrigger `
  -Once `
  -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes 1) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Seconds 55) `
  -MultipleInstances IgnoreNew

# Only the small watchdog runs elevated so it can stop an unresponsive task.
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Highest
$Definition = New-ScheduledTask `
  -Action $Action `
  -Trigger @($RepeatTrigger, $LogonTrigger) `
  -Settings $Settings `
  -Principal $Principal `
  -Description "Checks TradingBot /livez and MT5 every minute; recovers the WebApp with cooldown and starts MT5 when missing."

Register-ScheduledTask -TaskName $TaskName -InputObject $Definition -Force | Out-Null
if ($RunNow) {
  Start-ScheduledTask -TaskName $TaskName
}

$Registered = Get-ScheduledTask -TaskName $TaskName
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered watchdog '$TaskName' for '$UserId'."
Write-Host "State=$($Registered.State) LastResult=$($Info.LastTaskResult)"
Write-Host "It checks http://127.0.0.1:8000/livez and MT5 every minute."
Write-Host "WebApp recovery requires two consecutive failures and has a restart cooldown."
