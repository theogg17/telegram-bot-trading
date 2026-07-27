param(
  [string]$Root = "",
  [string]$WebAppTaskName = "TradingBotWebApp",
  [string]$WatchdogTaskName = "TradingBotWebAppWatchdog",
  [string]$Mt5TaskName = "TradingBotMT5",
  [string]$LiveUrl = "http://127.0.0.1:8000/livez",
  [string]$HealthUrl = "http://127.0.0.1:8000/healthz",
  [string]$Mt5Path = "C:\Program Files\MetaTrader 5\terminal64.exe",
  [ValidateSet("Serve", "Funnel", "Either")][string]$TailscaleMode = "Serve",
  [ValidateRange(1, 168)][int]$BackupMaxAgeHours = 30,
  [switch]$RequireLector,
  [switch]$RequireOperador,
  [switch]$AsJson
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Root)) {
  $Root = [string](Resolve-Path (Join-Path $PSScriptRoot ".."))
} else {
  $Root = [string](Resolve-Path -LiteralPath $Root)
}
$Results = New-Object System.Collections.Generic.List[object]

function Add-Check {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("PASS", "WARN", "FAIL")][string]$Level,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Message
  )
  $script:Results.Add([pscustomobject]@{ level = $Level; check = $Name; message = $Message })
}

function Get-HttpJson {
  param([Parameter(Mandatory = $true)][string]$Url)
  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 8
    $Payload = $null
    try { $Payload = $Response.Content | ConvertFrom-Json } catch {}
    return [pscustomobject]@{ reachable = $true; code = [int]$Response.StatusCode; payload = $Payload; error = "" }
  } catch {
    $HttpResponse = $_.Exception.Response
    if ($null -ne $HttpResponse) {
      $Body = ""
      try {
        $Reader = New-Object System.IO.StreamReader($HttpResponse.GetResponseStream())
        try { $Body = $Reader.ReadToEnd() } finally { $Reader.Dispose() }
      } catch {}
      $Payload = $null
      try { $Payload = $Body | ConvertFrom-Json } catch {}
      return [pscustomobject]@{ reachable = $true; code = [int]$HttpResponse.StatusCode; payload = $Payload; error = $_.Exception.Message }
    }
    return [pscustomobject]@{ reachable = $false; code = 0; payload = $null; error = $_.Exception.Message }
  }
}

function Check-Task {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][ValidateSet("WebApp", "Watchdog", "MT5")][string]$Role
  )
  try {
    $Task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    $Info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction Stop
    if ([string]$Task.State -eq "Disabled") {
      Add-Check FAIL "task.$Role" "$Name is disabled"
      return
    }

    $ExpectedState = if ($Role -eq "WebApp") { @("Running") } else { @("Ready", "Running") }
    if ($ExpectedState -notcontains [string]$Task.State) {
      Add-Check FAIL "task.$Role" "$Name state=$($Task.State)"
    } else {
      Add-Check PASS "task.$Role" "$Name state=$($Task.State)"
    }

    $ActionText = (($Task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)" }) -join " ")
    if ($Role -in @("WebApp", "Watchdog") -and $ActionText.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
      Add-Check FAIL "task.$Role.path" "$Name does not point to the canonical deployment"
    } elseif ($Role -eq "MT5" -and $ActionText.IndexOf($Mt5Path, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
      Add-Check FAIL "task.$Role.path" "$Name does not point to the expected terminal"
    } else {
      Add-Check PASS "task.$Role.path" "$Name action path is correct"
    }

    if ([string]$Task.Settings.MultipleInstances -ne "IgnoreNew") {
      Add-Check FAIL "task.$Role.singleton" "$Name MultipleInstances=$($Task.Settings.MultipleInstances)"
    } else {
      Add-Check PASS "task.$Role.singleton" "$Name ignores duplicate starts"
    }
    if ($Role -in @("WebApp", "MT5") -and [string]$Task.Settings.ExecutionTimeLimit -ne "PT0S") {
      Add-Check FAIL "task.$Role.limit" "$Name ExecutionTimeLimit=$($Task.Settings.ExecutionTimeLimit)"
    }
    if ($Role -eq "Watchdog") {
      if ($Info.LastRunTime -eq [DateTime]::MinValue) {
        Add-Check WARN "task.Watchdog.last_run" "Watchdog has not run yet"
      } elseif (((Get-Date) - $Info.LastRunTime).TotalMinutes -gt 3) {
        Add-Check FAIL "task.Watchdog.last_run" "Last watchdog run is older than 3 minutes"
      } elseif ($Info.LastTaskResult -ne 0) {
        Add-Check WARN "task.Watchdog.last_result" "LastResult=$($Info.LastTaskResult); inspect watchdog log"
      } else {
        Add-Check PASS "task.Watchdog.last_run" "Watchdog is executing every minute"
      }
    }
  } catch {
    Add-Check FAIL "task.$Role" "$Name is missing or unreadable"
  }
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$PrincipalObject = New-Object Security.Principal.WindowsPrincipal($Identity)
if ($PrincipalObject.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Add-Check PASS "permissions" "running elevated"
} else {
  Add-Check FAIL "permissions" "run this check from PowerShell as Administrator"
}

try {
  $Scheduler = Get-Service -Name "Schedule" -ErrorAction Stop
  if ($Scheduler.Status -eq "Running") { Add-Check PASS "scheduler" "Task Scheduler is running" }
  else { Add-Check FAIL "scheduler" "Task Scheduler status=$($Scheduler.Status)" }
} catch { Add-Check FAIL "scheduler" "Task Scheduler service not available" }

Check-Task -Name $WebAppTaskName -Role WebApp
Check-Task -Name $WatchdogTaskName -Role Watchdog
Check-Task -Name $Mt5TaskName -Role MT5

$Live = Get-HttpJson -Url $LiveUrl
if ($Live.reachable -and $Live.code -eq 200 -and $null -ne $Live.payload -and [string]$Live.payload.status -eq "ok") {
  Add-Check PASS "http.livez" "HTTP 200 status=ok"
} else {
  Add-Check FAIL "http.livez" "liveness failed code=$($Live.code)"
}

$Health = Get-HttpJson -Url $HealthUrl
if (-not $Health.reachable -or $null -eq $Health.payload) {
  Add-Check FAIL "http.healthz" "health endpoint unavailable or invalid"
} else {
  $HealthStatus = [string]$Health.payload.status
  if ($HealthStatus -eq "ok") { Add-Check PASS "http.healthz" "status=ok" }
  elseif ($HealthStatus -eq "degraded") { Add-Check WARN "http.healthz" "status=degraded" }
  else { Add-Check FAIL "http.healthz" "status=$HealthStatus code=$($Health.code)" }

  if ($null -ne $Health.payload.checks.db -and [bool]$Health.payload.checks.db.ok) {
    Add-Check PASS "health.database" "SQLite responds"
  } else {
    Add-Check FAIL "health.database" "SQLite health check failed"
  }

  foreach ($Worker in @(
    [pscustomobject]@{ name = "lector"; required = [bool]$RequireLector },
    [pscustomobject]@{ name = "operador"; required = [bool]$RequireOperador }
  )) {
    $Runtime = $Health.payload.checks.runtime.($Worker.name)
    $AutoEnabled = [bool]$Health.payload.checks.auto_start.("$($Worker.name)_enabled")
    $Running = $null -ne $Runtime -and [bool]$Runtime.running
    $Desired = $null -ne $Runtime -and [bool]$Runtime.desired_running
    if ($Worker.required -and (-not $AutoEnabled -or -not $Running -or -not $Desired)) {
      Add-Check FAIL "worker.$($Worker.name)" "required but auto_start=$AutoEnabled running=$Running desired=$Desired"
    } elseif (-not $Worker.required -and -not $Running) {
      Add-Check WARN "worker.$($Worker.name)" "intentionally not required and currently stopped"
    } else {
      Add-Check PASS "worker.$($Worker.name)" "auto_start=$AutoEnabled running=$Running desired=$Desired"
    }
  }
}

try {
  $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction Stop)
  $Loopback = @($Listeners | Where-Object { $_.LocalAddress -eq "127.0.0.1" })
  $Unsafe = @($Listeners | Where-Object { $_.LocalAddress -ne "127.0.0.1" })
  if ($Loopback.Count -eq 1 -and $Unsafe.Count -eq 0) {
    Add-Check PASS "network.port8000" "exactly one loopback listener"
  } else {
    Add-Check FAIL "network.port8000" "loopback_listeners=$($Loopback.Count) unsafe_listeners=$($Unsafe.Count)"
  }
} catch { Add-Check FAIL "network.port8000" "cannot inspect port 8000" }

try {
  $Processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
  function Get-RoleRootCount {
    param([string]$Pattern)
    $Matches = @($Processes | Where-Object { [string]$_.CommandLine -match $Pattern })
    $Ids = @{}
    foreach ($Process in $Matches) { $Ids[[int]$Process.ProcessId] = $true }
    $Roots = @($Matches | Where-Object { -not $Ids.ContainsKey([int]$_.ParentProcessId) })
    return [int]$Roots.Count
  }
  foreach ($Role in @(
    [pscustomobject]@{ name = "webapp"; pattern = '(?i)webapp[\\/]app\.py'; expected = 1 },
    [pscustomobject]@{ name = "lector"; pattern = '(?i)Lector[\\/]main\.py'; expected = $(if ($RequireLector) { 1 } else { 0 }) },
    [pscustomobject]@{ name = "operador"; pattern = '(?i)Operador[\\/]daemon\.py'; expected = $(if ($RequireOperador) { 1 } else { 0 }) }
  )) {
    $Count = Get-RoleRootCount -Pattern $Role.pattern
    if ($Count -gt 1) { Add-Check FAIL "process.$($Role.name)" "duplicate process groups=$Count" }
    elseif ($Count -eq $Role.expected) { Add-Check PASS "process.$($Role.name)" "process groups=$Count" }
    elseif ($Role.expected -eq 0 -and $Count -eq 1) { Add-Check WARN "process.$($Role.name)" "running although not required by this check" }
    else { Add-Check FAIL "process.$($Role.name)" "expected=$($Role.expected) process groups=$Count" }
  }

  $Mt5Processes = @($Processes | Where-Object { $_.Name -ieq "terminal64.exe" })
  if ($Mt5Processes.Count -eq 1 -and [int]$Mt5Processes[0].SessionId -gt 0) {
    Add-Check PASS "process.mt5" "one terminal in an interactive session"
  } else {
    Add-Check FAIL "process.mt5" "terminal_count=$($Mt5Processes.Count); expected one interactive instance"
  }
} catch { Add-Check FAIL "processes" "cannot inspect process uniqueness" }

try {
  $TailscaleService = Get-Service -Name "Tailscale" -ErrorAction Stop
  $TailscaleCim = Get-CimInstance Win32_Service -Filter "Name='Tailscale'" -ErrorAction Stop
  if ($TailscaleService.Status -eq "Running" -and $TailscaleCim.StartMode -eq "Auto") {
    Add-Check PASS "tailscale.service" "running and automatic"
  } else {
    Add-Check FAIL "tailscale.service" "status=$($TailscaleService.Status) start_mode=$($TailscaleCim.StartMode)"
  }

  $TailscaleExe = "C:\Program Files\Tailscale\tailscale.exe"
  $TsStatus = (& $TailscaleExe status --json 2>$null | ConvertFrom-Json)
  if ([string]$TsStatus.BackendState -eq "Running" -and [bool]$TsStatus.Self.Online) {
    Add-Check PASS "tailscale.peer" "backend running and node online"
  } else {
    Add-Check FAIL "tailscale.peer" "node is not online"
  }
  $ServeStatus = (& $TailscaleExe serve status 2>&1 | Out-String)
  $HasProxy = $ServeStatus -match 'proxy\s+http://127\.0\.0\.1:8000'
  $IsServe = $ServeStatus -match 'tailnet only'
  $IsFunnel = $ServeStatus -match 'Funnel on|available on the internet|public'
  $ModeOk = $HasProxy -and (($TailscaleMode -eq "Either") -or ($TailscaleMode -eq "Serve" -and $IsServe) -or ($TailscaleMode -eq "Funnel" -and $IsFunnel))
  if ($ModeOk) { Add-Check PASS "tailscale.proxy" "mode=$TailscaleMode proxy points to loopback" }
  else { Add-Check FAIL "tailscale.proxy" "Serve/Funnel configuration does not match expected mode=$TailscaleMode" }

  $UrlMatch = [regex]::Match($ServeStatus, 'https://[^\s]+')
  if ($UrlMatch.Success) {
    $RemoteBase = $UrlMatch.Value.TrimEnd('/')
    $RemoteLive = Get-HttpJson -Url "$RemoteBase/livez"
    if ($RemoteLive.code -eq 200 -and [string]$RemoteLive.payload.status -eq "ok") {
      Add-Check PASS "tailscale.https" "private HTTPS endpoint responds"
    } else {
      Add-Check FAIL "tailscale.https" "private HTTPS liveness failed code=$($RemoteLive.code)"
    }
    $RemoteAuth = Get-HttpJson -Url "$RemoteBase/api/status"
    if ($RemoteAuth.code -eq 401) { Add-Check PASS "tailscale.auth" "unauthenticated API request is rejected" }
    else { Add-Check FAIL "tailscale.auth" "unauthenticated API returned code=$($RemoteAuth.code)" }
  } else {
    Add-Check FAIL "tailscale.https" "HTTPS URL not found in Serve/Funnel status"
  }
} catch { Add-Check FAIL "tailscale" "Tailscale diagnostics failed" }

try {
  $BackupDir = Join-Path $Root "backups"
  $Backups = @(Get-ChildItem -LiteralPath $BackupDir -Filter "trading_bot_backup_*.zip" -File | Sort-Object LastWriteTimeUtc -Descending)
  if ($Backups.Count -eq 0) {
    Add-Check FAIL "backup.latest" "no backup ZIP found"
  } else {
    $Latest = $Backups[0]
    $AgeHours = ([DateTime]::UtcNow - $Latest.LastWriteTimeUtc).TotalHours
    if ($AgeHours -le $BackupMaxAgeHours) { Add-Check PASS "backup.age" ("latest age_hours={0:N1}" -f $AgeHours) }
    else { Add-Check FAIL "backup.age" ("latest age_hours={0:N1}" -f $AgeHours) }

    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $Verifier = Join-Path $Root "scripts\verify_backup.py"
    $VerifyJson = & $VenvPython $Verifier --json $Latest.FullName
    $VerifyExit = $LASTEXITCODE
    $Verify = $VerifyJson | ConvertFrom-Json
    if ($VerifyExit -eq 0 -and [bool]$Verify.ok -and [string]$Verify.db_integrity -eq "ok") {
      Add-Check PASS "backup.integrity" "ZIP CRC and SQLite integrity_check are valid"
    } else {
      Add-Check FAIL "backup.integrity" "latest backup failed verification"
    }
    if ($Backups.Count -ge 2) { Add-Check PASS "backup.generations" "generations=$($Backups.Count)" }
    else { Add-Check WARN "backup.generations" "only one backup generation exists" }
  }
  $StaleTemps = @(Get-ChildItem -LiteralPath $BackupDir -Filter "*.zip.tmp" -File -ErrorAction SilentlyContinue | Where-Object { ([DateTime]::UtcNow - $_.LastWriteTimeUtc).TotalMinutes -gt 15 })
  if ($StaleTemps.Count -eq 0) { Add-Check PASS "backup.temp" "no stale temporary ZIP" }
  else { Add-Check FAIL "backup.temp" "stale temporary ZIP count=$($StaleTemps.Count)" }
} catch { Add-Check FAIL "backup" "backup diagnostics failed" }

$FailCount = @($Results | Where-Object { $_.level -eq "FAIL" }).Count
$WarnCount = @($Results | Where-Object { $_.level -eq "WARN" }).Count
$ExitCode = if ($FailCount -gt 0) { 2 } elseif ($WarnCount -gt 0) { 1 } else { 0 }

if ($AsJson) {
  [pscustomobject]@{
    status = $(if ($ExitCode -eq 0) { "ok" } elseif ($ExitCode -eq 1) { "warning" } else { "error" })
    exit_code = $ExitCode
    pass = @($Results | Where-Object { $_.level -eq "PASS" }).Count
    warn = $WarnCount
    fail = $FailCount
    checks = $Results
  } | ConvertTo-Json -Depth 6
} else {
  $Results | Format-Table -AutoSize
  Write-Host "Summary: PASS=$(@($Results | Where-Object { $_.level -eq 'PASS' }).Count) WARN=$WarnCount FAIL=$FailCount EXIT=$ExitCode"
}
exit $ExitCode
