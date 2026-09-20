param(
    [ValidateSet('preload','postload')]
    [string]$Stage = 'preload'
)

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
Assert-DockerRuntimeAvailable

$dwhUser = Require-EnvValue -Name 'DWH_USER'
$dwhDb = Require-EnvValue -Name 'DWH_DB'

if ($Stage -eq 'preload') {
    $scripts = @('staging.sql')
} else {
    $scripts = @(
        'pipeline_state.sql',
        'source_frontier.sql',
        'realtime_projections.sql',
        'sse_notify.sql',
        'alert_engine.sql',
        'backfill_control.sql',
        'quality_control.sql',
        'serving_indexes.sql'
    )
}

Push-Location $projectRoot
try {
    Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service 'warehouse-db' -TimeoutSeconds 180
    foreach ($script in $scripts) {
        Write-Host "Applying warehouse migration: $script"
        Invoke-Checked -Description "Warehouse migration '$script'" -Command {
            & docker compose exec -T warehouse-db psql -v ON_ERROR_STOP=1 -U $dwhUser -d $dwhDb -f "/opt/project/sql/warehouse/$script"
        }
    }
}
finally { Pop-Location }

Write-Host "WAREHOUSE $($Stage.ToUpperInvariant()) PROVISION PASS"
