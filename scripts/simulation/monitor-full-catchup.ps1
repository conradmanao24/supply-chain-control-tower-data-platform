Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeDir = Join-Path $projectRoot 'data\runtime\full-catchup'
$monitorLog = Join-Path $runtimeDir 'monitor.log'
$statusFile = Join-Path $runtimeDir 'status.txt'
$notifier = $env:SCT_NOTIFIER_SCRIPT
$monitorSql = Join-Path $projectRoot 'sql\simulation\monitor_full_catchup.sql'
$cleanupSql = Join-Path $projectRoot 'sql\simulation\cleanup_full_catchup.sql'
$targetDate = '2026-09-15'
$pollSeconds = 300

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Write-Status {
    param([string]$Status, [string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'
    @(
        "status=$Status"
        "timestamp=$stamp"
        "message=$Message"
        "monitor_log=$monitorLog"
    ) | Set-Content -Path $statusFile -Encoding UTF8
    "[$stamp] $Status - $Message" | Tee-Object -FilePath $monitorLog -Append
}

function Send-OptionalNotification {
    param(
        [ValidateSet('DONE','BLOCKED','FAILED','NEED_INPUT')]
        [string]$Status,
        [string]$Message
    )
    if ([string]::IsNullOrWhiteSpace($notifier) -or -not (Test-Path -LiteralPath $notifier)) {
        "NOTIFIER SKIPPED: set SCT_NOTIFIER_SCRIPT to enable external notifications." | Tee-Object -FilePath $monitorLog -Append
        return
    }
    try {
        & $notifier -Source 'Supply Chain Control Tower' -Status $Status -Message $Message | Tee-Object -FilePath $monitorLog -Append
    }
    catch {
        "NOTIFICATION ERROR: $($_.Exception.Message)" | Tee-Object -FilePath $monitorLog -Append
    }
}

function Get-CatchupState {
    $bash = 'export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"; exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -W -h -1 -s , -i /tmp/monitor_full_catchup.sql'
    $lines = & docker compose exec -T wwi-sqlserver /bin/bash -lc $bash 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "State query failed: $($lines -join ' ')"
    }
    $line = $lines | Where-Object { $_ -match '^\d{4}-\d{2}-\d{2},' } | Select-Object -Last 1
    if (-not $line) {
        throw "Could not parse catch-up state. Raw output: $($lines -join ' ')"
    }
    $parts = $line -split ','
    [pscustomobject]@{
        MaxOrderDate = $parts[0].Trim()
        OrderRows = [int64]$parts[1].Trim()
        TemporalTables = [int]$parts[2].Trim()
        SimulationTriggers = [int]$parts[3].Trim()
        DisabledFKs = [int]$parts[4].Trim()
        UntrustedFKs = [int]$parts[5].Trim()
    }
}

function Catchup-ProcessRunning {
    $top = (& docker compose top wwi-sqlserver 2>&1 | Out-String)
    return ($top -match '_parseonly_full_catchup\.sql')
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class MonitorPowerState {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
'@
$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]0x00000001
[void][MonitorPowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)

Push-Location $projectRoot
try {
    & docker compose cp $monitorSql 'wwi-sqlserver:/tmp/monitor_full_catchup.sql' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to copy monitor SQL into container.' }
    & docker compose cp $cleanupSql 'wwi-sqlserver:/tmp/cleanup_full_catchup.sql' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to copy cleanup SQL into container.' }

    Write-Host '============================================================'
    Write-Host ' WWI FULL CATCH-UP MONITOR'
    Write-Host " Target : $targetDate"
    Write-Host ' Poll   : every 5 minutes'
    Write-Host " Log    : $monitorLog"
    Write-Host ' This terminal will remain open after completion.'
    Write-Host '============================================================'

    $initial = Get-CatchupState
    Write-Status -Status 'RUNNING' -Message "Current MAX(OrderDate)=$($initial.MaxOrderDate), Orders=$($initial.OrderRows)."

    while (Catchup-ProcessRunning) {
        $state = Get-CatchupState
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        $msg = "[$stamp] progress MAX(OrderDate)=$($state.MaxOrderDate) Orders=$($state.OrderRows) Temporal=$($state.TemporalTables) SimTriggers=$($state.SimulationTriggers)"
        $msg | Tee-Object -FilePath $monitorLog -Append
        Start-Sleep -Seconds $pollSeconds
    }

    Start-Sleep -Seconds 5
    $final = Get-CatchupState

    $success = ($final.MaxOrderDate -eq $targetDate -and
                $final.TemporalTables -eq 17 -and
                $final.SimulationTriggers -eq 0 -and
                $final.DisabledFKs -eq 0 -and
                $final.UntrustedFKs -eq 0)

    if ($success) {
        Write-Status -Status 'DONE' -Message "WWI reached $targetDate. Orders=$($final.OrderRows). Temporal/FK validation PASS."
        Send-OptionalNotification -Status 'DONE' -Message "WWI full catch-up completed through 2026-09-15. MAX(OrderDate)=$($final.MaxOrderDate), Orders=$($final.OrderRows), temporal/FK validation passed."
        Write-Host '============================================================'
        Write-Host ' DONE - WWI FULL CATCH-UP PASS'
        Write-Host " MAX(OrderDate): $($final.MaxOrderDate)"
        Write-Host " Orders        : $($final.OrderRows)"
        Write-Host ' Optional completion notification processed.'
        Write-Host '============================================================'
    }
    else {
        if ($final.TemporalTables -lt 17 -or $final.SimulationTriggers -gt 0) {
            'Catch-up process ended with simulation state still active. Running official WWI cleanup...' | Tee-Object -FilePath $monitorLog -Append
            $bashCleanup = 'export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"; exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -i /tmp/cleanup_full_catchup.sql'
            & docker compose exec -T wwi-sqlserver /bin/bash -lc $bashCleanup 2>&1 | Tee-Object -FilePath $monitorLog -Append
            Start-Sleep -Seconds 2
            $final = Get-CatchupState
        }

        $reason = "Process ended before validated target. MAX(OrderDate)=$($final.MaxOrderDate), Temporal=$($final.TemporalTables), SimTriggers=$($final.SimulationTriggers), DisabledFK=$($final.DisabledFKs), UntrustedFK=$($final.UntrustedFKs)."
        Write-Status -Status 'BLOCKED' -Message $reason
        Send-OptionalNotification -Status 'BLOCKED' -Message "WWI full catch-up blocked. $reason Check the monitor terminal/log."
        Write-Host '============================================================'
        Write-Host ' BLOCKED - WWI FULL CATCH-UP'
        Write-Host $reason
        Write-Host ' Optional blocked notification processed.'
        Write-Host '============================================================'
    }
}
catch {
    $reason = $_.Exception.Message
    Write-Status -Status 'BLOCKED' -Message $reason
    Send-OptionalNotification -Status 'BLOCKED' -Message "WWI full catch-up monitor blocked. $reason"
    Write-Host '============================================================'
    Write-Host ' MONITOR BLOCKED'
    Write-Host $reason
    Write-Host '============================================================'
}
finally {
    [void][MonitorPowerState]::SetThreadExecutionState($ES_CONTINUOUS)
    Pop-Location
}



