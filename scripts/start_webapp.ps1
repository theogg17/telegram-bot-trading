param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "webapp_task_$Stamp.log"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

Set-Location $Root
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TRADING_BOT_HOST = $HostAddress
$env:TRADING_BOT_PORT = [string]$Port

"[$(Get-Date -Format s)] Starting Trading Bot WebApp from $Root" | Out-File -FilePath $LogFile -Encoding utf8 -Append
& $PythonExe "webapp\app.py" *>> $LogFile
