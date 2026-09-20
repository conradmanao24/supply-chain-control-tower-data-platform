Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$evidenceDir = Join-Path $projectRoot 'docs\source-audit\evidence\simulation'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
$outputPath = Join-Path $evidenceDir 'pilot_2016-06-01_to_2016-06-07.txt'

Push-Location $projectRoot
try {
    $containerId = (& docker compose ps -q wwi-sqlserver | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw 'wwi-sqlserver is not running.'
    }

    $health = (& docker inspect --format '{{.State.Health.Status}}' $containerId).Trim()
    if ($health -ne 'healthy') {
        throw "wwi-sqlserver is not healthy (status: $health)."
    }

    $command = 'export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"; exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -W -s , -i /opt/project/sql/audit/07_simulation_pilot.sql'
    $started = Get-Date
    $output = & docker compose exec -T wwi-sqlserver /bin/bash -lc $command 2>&1
    $exitCode = $LASTEXITCODE
    $finished = Get-Date

    @(
        "host_started_at=$($started.ToString('o'))",
        "host_finished_at=$($finished.ToString('o'))",
        "host_runtime_seconds=$([math]::Round(($finished - $started).TotalSeconds,3))",
        $output
    ) | Set-Content -Encoding utf8 $outputPath

    $output | Write-Host

    if ($exitCode -ne 0) {
        throw "source simulation pilot failed (exit code $exitCode). See $outputPath"
    }

    Write-Host "EVIDENCE=$outputPath"
    Write-Host 'SOURCE SIMULATION 7-DAY PILOT EXECUTION PASS'
}
finally {
    Pop-Location
}
