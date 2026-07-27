param(
  [string]$PythonCommand = "python",
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "backups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "queue\pending") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "queue\processed") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "queue\failed") | Out-Null

if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
  & $PythonCommand -m venv .venv
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create .venv with '$PythonCommand' (exit=$LASTEXITCODE)."
  }
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not $SkipInstall) {
  & $VenvPython -m pip install --upgrade pip
  if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed (exit=$LASTEXITCODE)."
  }
  & $VenvPython -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) {
    throw "dependency installation failed (exit=$LASTEXITCODE)."
  }
  & $VenvPython -m pip check
  if ($LASTEXITCODE -ne 0) {
    throw "pip check failed (exit=$LASTEXITCODE)."
  }
}

Write-Host "Server setup complete."
Write-Host "Next: run .\scripts\start_webapp.ps1 or register the task with .\scripts\register_webapp_task.ps1"
