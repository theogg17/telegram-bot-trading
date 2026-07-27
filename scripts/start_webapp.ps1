param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [int64]$LogMaxBytes = 5242880,
  [int]$LogBackups = 5
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir "webapp_task.log"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
  throw "Production Python not found: $VenvPython. Run scripts\setup_server.ps1 first."
}

function Rotate-TaskLog {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int64]$MaxBytes,
    [int]$Backups
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return
  }
  if ((Get-Item -LiteralPath $Path).Length -lt [Math]::Max(262144, $MaxBytes)) {
    return
  }

  $Keep = [Math]::Max(1, $Backups)
  $Oldest = "$Path.$Keep"
  if (Test-Path -LiteralPath $Oldest) {
    Remove-Item -LiteralPath $Oldest -Force
  }
  for ($Index = $Keep - 1; $Index -ge 1; $Index--) {
    $Source = "$Path.$Index"
    if (Test-Path -LiteralPath $Source) {
      Move-Item -LiteralPath $Source -Destination "$Path.$($Index + 1)" -Force
    }
  }
  Move-Item -LiteralPath $Path -Destination "$Path.1" -Force
}

function Write-TaskLog {
  param([Parameter(Mandatory = $true)][string]$Message)
  "[$(Get-Date -Format o)] $Message" | Out-File -FilePath $LogFile -Encoding utf8 -Append
}

Rotate-TaskLog -Path $LogFile -MaxBytes $LogMaxBytes -Backups $LogBackups

Set-Location $Root
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TRADING_BOT_HOST = $HostAddress
$env:TRADING_BOT_PORT = [string]$Port
# Production retention is bounded. The application still keeps 14 days of
# backups by default and archives database history according to its settings.
$env:TRADING_BOT_NO_DELETE_POLICY = "false"

Write-TaskLog "Starting Trading Bot WebApp root=$Root host=$HostAddress port=$Port python=$VenvPython"
# Windows PowerShell 5.1 maps any native stderr line to an ErrorRecord. Warnings
# from Python (for example a deprecation warning) must be logged, not mistaken
# for a failed process launch under ErrorActionPreference=Stop.
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $VenvPython "webapp\app.py" *>> $LogFile
$ExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($null -eq $ExitCode) {
  $ExitCode = 1
}
Write-TaskLog "WebApp exited code=$ExitCode; Task Scheduler will apply its recovery policy"

# A WebApp exit is always unexpected while this long-running task is active.
# Returning a failure code lets Task Scheduler restart it even if Python exits 0.
if ([int]$ExitCode -eq 0) {
  $ExitCode = 1
}
exit [int]$ExitCode
