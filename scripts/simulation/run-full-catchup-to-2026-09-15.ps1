Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sqlFile = Join-Path $projectRoot 'sql\simulation\full_catchup_to_2026-09-15.sql'
$runtimeDir = Join-Path $projectRoot 'data\runtime\full-catchup'
$logFile = Join-Path $runtimeDir 'full-catchup-to-2026-09-15.log'
$statusFile = Join-Path $runtimeDir 'status.txt'
$notifier = $env:SCT_NOTIFIER_SCRIPT
$containerSqlPath = '/tmp/full_catchup_to_2026-09-15.sql'
$sourceName = 'Supply Chain CT'

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Write-RunStatus {
    param([string]$Status, [string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'
    @(
        "status=$Status"
        "timestamp=$stamp"
        "message=$Message"
        "log=$logFile"
    ) | Set-Content -Path $statusFile -Encoding UTF8
    Write-Host "[$stamp] $Status - $Message"
}

function Send-OptionalNotification {
    param(
        [ValidateSet('DONE','BLOCKED','FAILED','NEED_INPUT')]
        [string]$Status,
        [string]$Message
    )
    if ([string]::IsNullOrWhiteSpace($notifier) -or -not (Test-Path -LiteralPath $notifier)) {
        "NOTIFIER SKIPPED: set SCT_NOTIFIER_SCRIPT to enable external notifications." | Tee-Object -FilePath $logFile -Append
        return
    }
    try {
        & $notifier -Source $sourceName -Status $Status -Message $Message | Tee-Object -FilePath $logFile -Append
    }
    catch {
        "NOTIFICATION ERROR: $($_.Exception.Message)" | Tee-Object -FilePath $logFile -Append
    }
}

# Prevent normal system-idle sleep while this terminal is running.
# Display sleep is still allowed. Closing the laptop lid can still suspend Windows.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CatchupPowerState {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
'@
$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]0x00000001

$started = Get-Date
Set-Content -Path $logFile -Value "FULL CATCH-UP LAUNCH | $($started.ToString('yyyy-MM-dd HH:mm:ss K'))" -Encoding UTF8
Write-RunStatus -Status 'RUNNING' -Message 'WWI full catch-up 2016-06-08 -> 2026-09-15 is running.'

[void][CatchupPowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)

Push-Location $projectRoot
try {
    if (-not (Test-Path $sqlFile)) {
        throw "SQL file not found: $sqlFile"
    }

    $containerId = (& docker compose ps -q wwi-sqlserver | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw 'wwi-sqlserver is not running.'
    }

    $health = (& docker inspect --format '{{.State.Health.Status}}' $containerId).Trim()
    if ($health -ne 'healthy') {
        throw "wwi-sqlserver is not healthy (status: $health)."
    }

    Write-Host ''
    Write-Host '============================================================'
    Write-Host ' WWI FULL CATCH-UP'
    Write-Host ' Start : 2016-06-08'
    Write-Host ' Target: 2026-09-15'
    Write-Host ' Progress is emitted per month.'
    Write-Host " Log   : $logFile"
    Write-Host '============================================================'
    Write-Host ''

    & docker compose cp $sqlFile "wwi-sqlserver:$containerSqlPath" 2>&1 | Tee-Object -FilePath $logFile -Append
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to copy full catch-up SQL into SQL Server container.'
    }

    $bashCommand = 'export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"; exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -r1 -i /tmp/full_catchup_to_2026-09-15.sql'
    & docker compose exec -T wwi-sqlserver /bin/bash -lc $bashCommand 2>&1 | Tee-Object -FilePath $logFile -Append
    $sqlExitCode = $LASTEXITCODE

    if ($sqlExitCode -ne 0) {
        throw "SQL catch-up exited with code $sqlExitCode."
    }

    if (-not (Select-String -Path $logFile -SimpleMatch 'FULL CATCH-UP PASS | target 2026-09-15 reached and validation passed' -Quiet)) {
        throw 'SQL process exited successfully but PASS marker was not found in the log.'
    }

    $finished = Get-Date
    $duration = $finished - $started
    $durationText = '{0:dd\.hh\:mm\:ss}' -f $duration
    Write-RunStatus -Status 'DONE' -Message "WWI catch-up reached 2026-09-15 and validation passed. Runtime $durationText."
    Send-OptionalNotification -Status 'DONE' -Message "WWI full catch-up completed through 2026-09-15. Validation passed. Runtime: $durationText."

    Write-Host ''
    Write-Host '============================================================'
    Write-Host ' DONE - WWI reached 2026-09-15'
    Write-Host " Runtime: $durationText"
    Write-Host " Log    : $logFile"
    Write-Host ' Optional completion notification processed.'
    Write-Host '============================================================'
}
catch {
    $failed = Get-Date
    $duration = $failed - $started
    $durationText = '{0:dd\.hh\:mm\:ss}' -f $duration
    $message = $_.Exception.Message
    "FULL CATCH-UP BLOCKED | $message" | Tee-Object -FilePath $logFile -Append
    Write-RunStatus -Status 'BLOCKED' -Message "$message Runtime $durationText."
    Send-OptionalNotification -Status 'BLOCKED' -Message "WWI full catch-up blocked. $message Runtime: $durationText. Check the terminal/log."

    Write-Host ''
    Write-Host '============================================================'
    Write-Host ' BLOCKED - full catch-up did not complete'
    Write-Host " Reason : $message"
    Write-Host " Runtime: $durationText"
    Write-Host " Log    : $logFile"
    Write-Host ' Optional blocked notification processed.'
    Write-Host '============================================================'
}
finally {
    [void][CatchupPowerState]::SetThreadExecutionState($ES_CONTINUOUS)
    Pop-Location
}

