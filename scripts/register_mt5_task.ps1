param(
  [string]$TaskName = "TradingBotMT5",
  [string]$TerminalPath = "C:\Program Files\MetaTrader 5\terminal64.exe",
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $TerminalPath -PathType Leaf)) {
  throw "MetaTrader terminal not found: $TerminalPath"
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$PrincipalObject = New-Object Security.Principal.WindowsPrincipal($Identity)
$AdminRole = [Security.Principal.WindowsBuiltInRole]::Administrator
if (-not $PrincipalObject.IsInRole($AdminRole)) {
  throw "Run this script from PowerShell as Administrator."
}

$UserId = $Identity.Name
$Action = New-ScheduledTaskAction `
  -Execute $TerminalPath `
  -WorkingDirectory (Split-Path -Parent $TerminalPath)
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 10 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Definition = New-ScheduledTask `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Principal $Principal `
  -Description "XM/MetaTrader 5 terminal for TradingBot. Runs in the interactive Windows session."

Register-ScheduledTask -TaskName $TaskName -InputObject $Definition -Force | Out-Null
if ($RunNow) {
  if (Get-Process -Name "terminal64" -ErrorAction SilentlyContinue) {
    Write-Host "MetaTrader is already running; no second instance was started."
  } else {
    Start-ScheduledTask -TaskName $TaskName
  }
}

$Registered = Get-ScheduledTask -TaskName $TaskName
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered MT5 task '$TaskName' for '$UserId'."
Write-Host "State=$($Registered.State) LastResult=$($Info.LastTaskResult)"
Write-Host "It starts at logon and keeps running after RDP is disconnected."
