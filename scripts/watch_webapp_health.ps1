param(
  [string]$TaskName = "TradingBotWebApp",
  [string]$HealthUrl = "http://127.0.0.1:8000/healthz"
)

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "webapp_watchdog.log"

function Write-WatchLog {
  param([string]$Message)
  "[$(Get-Date -Format s)] $Message" | Out-File -FilePath $LogFile -Encoding utf8 -Append
}

function Send-WatchAlert {
  param([string]$Message)
  $Webhook = [string]$env:TRADING_BOT_WATCHDOG_DISCORD_WEBHOOK
  if ([string]::IsNullOrWhiteSpace($Webhook)) {
    return
  }
  try {
    $Body = @{ content = "[CRITICAL] TradingBot WebApp watchdog`n$Message" } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri $Webhook -Method Post -ContentType "application/json" -Body $Body -TimeoutSec 8 | Out-Null
  } catch {
    Write-WatchLog "discord alert failed: $($_.Exception.Message)"
  }
}

$ShouldRestart = $false
$AlertMessage = ""

try {
  $res = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 5
  if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 600) {
    Write-WatchLog "health reachable status=$($res.StatusCode)"
    exit 0
  }
  Write-WatchLog "health returned status=$($res.StatusCode); restarting task"
  $ShouldRestart = $true
  $AlertMessage = "health returned status=$($res.StatusCode)"
} catch {
  if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
    Write-WatchLog "health reachable status=$([int]$_.Exception.Response.StatusCode)"
    exit 0
  }
  $ShouldRestart = $true
  $AlertMessage = "health unreachable: $($_.Exception.Message)"
  Write-WatchLog "$AlertMessage; restarting task"
}

if (-not $ShouldRestart) {
  exit 0
}

Send-WatchAlert $AlertMessage

try {
  schtasks.exe /Run /TN $TaskName | Out-Null
  Write-WatchLog "task start requested: $TaskName"
} catch {
  Write-WatchLog "task start failed: $($_.Exception.Message)"
  exit 1
}
