param(
  [string]$TaskName = "TradingBotWebApp",
  [string]$Mt5TaskName = "TradingBotMT5",
  [string]$Mt5ProcessName = "terminal64",
  [string]$HealthUrl = "http://127.0.0.1:8000/livez",
  [ValidateRange(1, 10)][int]$FailureThreshold = 2,
  [ValidateRange(30, 3600)][int]$RestartCooldownSec = 180,
  [ValidateRange(5, 120)][int]$RecoveryWaitSec = 30,
  [ValidateRange(5, 45)][int]$Mt5RecoveryWaitSec = 20,
  [int64]$LogMaxBytes = 2097152,
  [ValidateRange(1, 20)][int]$LogBackups = 5,
  [switch]$SkipMt5Recovery
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "webapp_watchdog.log"
$StateFile = Join-Path $LogDir "webapp_watchdog_state.json"

function Rotate-WatchLog {
  if (-not (Test-Path -LiteralPath $LogFile -PathType Leaf)) {
    return
  }
  if ((Get-Item -LiteralPath $LogFile).Length -lt [Math]::Max(262144, $LogMaxBytes)) {
    return
  }
  $Oldest = "$LogFile.$LogBackups"
  if (Test-Path -LiteralPath $Oldest) {
    Remove-Item -LiteralPath $Oldest -Force
  }
  for ($Index = $LogBackups - 1; $Index -ge 1; $Index--) {
    $Source = "$LogFile.$Index"
    if (Test-Path -LiteralPath $Source) {
      Move-Item -LiteralPath $Source -Destination "$LogFile.$($Index + 1)" -Force
    }
  }
  Move-Item -LiteralPath $LogFile -Destination "$LogFile.1" -Force
}

function Write-WatchLog {
  param([Parameter(Mandatory = $true)][string]$Message)
  Rotate-WatchLog
  "[$([DateTime]::UtcNow.ToString('o'))] $Message" | Out-File -FilePath $LogFile -Encoding utf8 -Append
}

function Read-WatchState {
  $State = [ordered]@{
    failure_count = 0
    last_restart_utc = ""
    last_ok_utc = ""
    last_heartbeat_utc = ""
    last_error = ""
    last_mt5_ok_utc = ""
    last_mt5_restart_utc = ""
    last_mt5_error = ""
  }
  if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) {
    return $State
  }
  try {
    $Saved = Get-Content -Raw -LiteralPath $StateFile | ConvertFrom-Json
    foreach ($Name in @($State.Keys)) {
      if ($Saved.PSObject.Properties.Name -contains $Name) {
        $State[$Name] = $Saved.$Name
      }
    }
  } catch {
    Write-WatchLog "state file invalid; resetting it: $($_.Exception.Message)"
  }
  return $State
}

function Save-WatchState {
  param([Parameter(Mandatory = $true)]$State)
  $TempFile = "$StateFile.tmp"
  $State | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $TempFile -Encoding utf8
  Move-Item -LiteralPath $TempFile -Destination $StateFile -Force
}

function Test-HealthPayload {
  param([string]$Content)
  if ([string]::IsNullOrWhiteSpace($Content)) {
    return $false
  }
  try {
    $Payload = $Content | ConvertFrom-Json
    return (
      $null -ne $Payload -and
      $Payload.PSObject.Properties.Name -contains "status" -and
      [string]$Payload.status -eq "ok"
    )
  } catch {
    return $false
  }
}

$script:LastHealthError = ""
function Test-WebAppLiveness {
  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 5
    if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300 -and (Test-HealthPayload -Content $Response.Content)) {
      return $true
    }
    $script:LastHealthError = "unexpected status=$($Response.StatusCode) or invalid JSON"
    return $false
  } catch {
    $HttpResponse = $_.Exception.Response
    if ($null -ne $HttpResponse) {
      try {
        $script:LastHealthError = "http_status=$([int]$HttpResponse.StatusCode)"
      } catch {
        $script:LastHealthError = $_.Exception.Message
      }
    } else {
      $script:LastHealthError = $_.Exception.Message
    }
    return $false
  }
}

function Get-Mt5ProcessesForCurrentSession {
  $CurrentSessionId = (Get-Process -Id $PID -ErrorAction Stop).SessionId
  return @(
    Get-Process -Name $Mt5ProcessName -ErrorAction SilentlyContinue |
      Where-Object { $_.SessionId -eq $CurrentSessionId }
  )
}

$script:LastMt5Error = ""
$script:Mt5Restarted = $false
function Ensure-Mt5Running {
  $Processes = @(Get-Mt5ProcessesForCurrentSession)
  if ($Processes.Count -eq 1) {
    return $true
  }
  if ($Processes.Count -gt 1) {
    $script:LastMt5Error = "multiple MT5 processes in watchdog session count=$($Processes.Count)"
    return $false
  }

  try {
    $Task = Get-ScheduledTask -TaskName $Mt5TaskName -ErrorAction Stop
    if ([string]$Task.State -eq "Disabled") {
      throw "scheduled task is disabled"
    }

    Write-WatchLog "MT5 missing; starting task name=$Mt5TaskName"
    Start-ScheduledTask -TaskName $Mt5TaskName -ErrorAction Stop | Out-Null
    $script:Mt5Restarted = $true

    $Deadline = [DateTime]::UtcNow.AddSeconds($Mt5RecoveryWaitSec)
    do {
      Start-Sleep -Seconds 2
      $Processes = @(Get-Mt5ProcessesForCurrentSession)
      if ($Processes.Count -eq 1) {
        Write-WatchLog "MT5 recovered task=$Mt5TaskName"
        return $true
      }
      if ($Processes.Count -gt 1) {
        $script:LastMt5Error = "MT5 recovery created multiple processes count=$($Processes.Count)"
        return $false
      }
    } while ([DateTime]::UtcNow -lt $Deadline)

    $script:LastMt5Error = "MT5 did not appear within $Mt5RecoveryWaitSec seconds"
    return $false
  } catch {
    $script:LastMt5Error = $_.Exception.Message
    return $false
  }
}

function Send-WatchAlert {
  param([Parameter(Mandatory = $true)][string]$Message)
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

$State = Read-WatchState
$NowUtc = [DateTime]::UtcNow

if (Test-WebAppLiveness) {
  if (-not $SkipMt5Recovery) {
    if (-not (Ensure-Mt5Running)) {
      $State.last_mt5_error = [string]$script:LastMt5Error
      if ($script:Mt5Restarted) {
        $State.last_mt5_restart_utc = [DateTime]::UtcNow.ToString("o")
      }
      Save-WatchState -State $State
      $Message = "MT5 health recovery failed task=$Mt5TaskName error=$($State.last_mt5_error)"
      Write-WatchLog $Message
      Send-WatchAlert $Message
      exit 1
    }
    $State.last_mt5_ok_utc = $NowUtc.ToString("o")
    $State.last_mt5_error = ""
    if ($script:Mt5Restarted) {
      $State.last_mt5_restart_utc = [DateTime]::UtcNow.ToString("o")
    }
  }

  $HadFailures = [int]$State.failure_count -gt 0
  $State.failure_count = 0
  $State.last_ok_utc = $NowUtc.ToString("o")
  $State.last_error = ""

  $WriteHeartbeat = [string]::IsNullOrWhiteSpace([string]$State.last_heartbeat_utc)
  if (-not $WriteHeartbeat) {
    try {
      $LastHeartbeat = [DateTime]::Parse([string]$State.last_heartbeat_utc).ToUniversalTime()
      $WriteHeartbeat = ($NowUtc - $LastHeartbeat).TotalHours -ge 6
    } catch {
      $WriteHeartbeat = $true
    }
  }
  if ($HadFailures) {
    Write-WatchLog "health recovered url=$HealthUrl"
  } elseif ($WriteHeartbeat) {
    Write-WatchLog "heartbeat healthy url=$HealthUrl"
  }
  if ($WriteHeartbeat) {
    $State.last_heartbeat_utc = $NowUtc.ToString("o")
  }
  Save-WatchState -State $State
  exit 0
}

$State.failure_count = [int]$State.failure_count + 1
$State.last_error = [string]$script:LastHealthError
Write-WatchLog "health failure $($State.failure_count)/$FailureThreshold url=$HealthUrl error=$($State.last_error)"
Save-WatchState -State $State

if ([int]$State.failure_count -lt $FailureThreshold) {
  exit 1
}

$LastRestart = [DateTime]::MinValue
if (-not [string]::IsNullOrWhiteSpace([string]$State.last_restart_utc)) {
  $ParsedRestart = [DateTime]::MinValue
  if ([DateTime]::TryParse([string]$State.last_restart_utc, [ref]$ParsedRestart)) {
    $LastRestart = $ParsedRestart.ToUniversalTime()
  }
}
if (($NowUtc - $LastRestart).TotalSeconds -lt $RestartCooldownSec) {
  Write-WatchLog "restart suppressed by cooldown seconds=$RestartCooldownSec"
  exit 1
}

try {
  $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  if ([string]$Task.State -eq "Running") {
    Write-WatchLog "stopping unresponsive task name=$TaskName"
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    for ($Index = 0; $Index -lt 10; $Index++) {
      Start-Sleep -Seconds 1
      if ([string](Get-ScheduledTask -TaskName $TaskName).State -ne "Running") {
        break
      }
    }
  }

  Write-WatchLog "starting task name=$TaskName"
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  $State.last_restart_utc = [DateTime]::UtcNow.ToString("o")
  Save-WatchState -State $State
} catch {
  $Message = "task recovery failed name=$TaskName error=$($_.Exception.Message)"
  Write-WatchLog $Message
  Send-WatchAlert $Message
  exit 1
}

$Deadline = [DateTime]::UtcNow.AddSeconds($RecoveryWaitSec)
do {
  Start-Sleep -Seconds 2
  if (Test-WebAppLiveness) {
    $State.failure_count = 0
    $State.last_ok_utc = [DateTime]::UtcNow.ToString("o")
    $State.last_error = ""
    Save-WatchState -State $State
    Write-WatchLog "task recovered name=$TaskName url=$HealthUrl"
    exit 0
  }
} while ([DateTime]::UtcNow -lt $Deadline)

$Message = "task did not recover name=$TaskName wait_seconds=$RecoveryWaitSec error=$($script:LastHealthError)"
Write-WatchLog $Message
Send-WatchAlert $Message
exit 1
