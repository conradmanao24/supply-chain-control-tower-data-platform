Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$evidenceDir = Join-Path $projectRoot 'docs\source-audit\evidence\audit'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null

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

    $auditFiles = @(
        '01_schema_inventory.sql',
        '02_table_row_counts.sql',
        '03_primary_keys.sql',
        '04_foreign_keys.sql',
        '05_date_ranges.sql',
        '06_incremental_candidates.sql'
    )

    foreach ($file in $auditFiles) {
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($file)
        $containerPath = "/opt/project/sql/audit/$file"
        $command = 'export SQLCMDPASSWORD="$MSSQL_SA_PASSWORD"; exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -W -s , -i ' + $containerPath
        $output = & docker compose exec -T wwi-sqlserver /bin/bash -lc $command 2>&1
        $exitCode = $LASTEXITCODE
        $outputPath = Join-Path $evidenceDir "$stem.txt"
        $output | Set-Content -Encoding utf8 $outputPath

        if ($exitCode -ne 0) {
            throw "Audit query failed: $file (exit code $exitCode). See $outputPath"
        }

        Write-Host "PASS $file -> $outputPath"
    }
}
finally {
    Pop-Location
}

Write-Host 'SOURCE AUDIT AUDIT QUERY EXECUTION PASS'
