param()

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
Assert-DockerRuntimeAvailable

$database = Require-EnvValue -Name 'WWI_DATABASE'
$saPassword = Require-EnvValue -Name 'MSSQL_SA_PASSWORD'
$readerPassword = Require-EnvValue -Name 'WWI_SOURCE_PASSWORD'
$eventPassword = Require-EnvValue -Name 'WWI_EVENT_PASSWORD'

$scripts = @(
    'source_event.sql',
    'extraction_views.sql',
    'incremental_extraction.sql',
    'business_event_publication.sql',
    'telemetry_publish_wrapper.sql',
    'deadline_timer.sql',
    'current_state_reads.sql',
    'dead_letter.sql',
    'ingress_cleanup.sql',
    'telemetry_event_refinement.sql'
)

Push-Location $projectRoot
try {
    Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service 'wwi-sqlserver' -TimeoutSeconds 300
    $sqlcmd = Get-SqlCmdPath -ProjectRoot $projectRoot
    foreach ($script in $scripts) {
        Write-Host "Applying SQL Server integration: $script"
        Invoke-Checked -Description "Source integration script '$script'" -Command {
            & docker compose exec -T wwi-sqlserver $sqlcmd -S localhost -U sa -P $saPassword -C -b -i "/opt/project/sql/infrastructure/$script" -v "DatabaseName=$database" "SCT_READER_PASSWORD=$readerPassword" "SCT_EVENT_PASSWORD=$eventPassword"
        }
    }
}
finally { Pop-Location }

Write-Host 'SOURCE INTEGRATION PROVISION PASS'
