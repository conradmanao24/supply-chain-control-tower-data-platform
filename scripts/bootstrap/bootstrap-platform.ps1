param()

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
Assert-DockerRuntimeAvailable
Assert-LocalPasswordConfigured
Assert-PlatformSecretsConfigured

Write-Host '=== Supply Chain Control Tower portfolio bootstrap ==='

# 1. Restore the frozen 2026-09-15 source baseline and validate SQL Server.
& "$PSScriptRoot\restore-portfolio-baseline.ps1"

# 2. Recreate all project-owned SQL Server integration objects.
& "$PSScriptRoot\provision-source-integration.ps1"

Push-Location $projectRoot
try {
    # 3. Build the project-owned Airflow/dbt runtime image.
    Write-Host 'Building Airflow/dbt runtime image...'
    Invoke-Checked -Description 'Airflow image build' -Command { & docker compose build airflow-init }

    # 4. Start persistent PostgreSQL services and initialize the writable dbt runtime volume.
    Invoke-Checked -Description 'PostgreSQL startup' -Command { & docker compose up -d warehouse-db airflow-db }
    Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service 'warehouse-db' -TimeoutSeconds 180
    Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service 'airflow-db' -TimeoutSeconds 180

    Invoke-Checked -Description 'dbt runtime initialization' -Command { & docker compose run --rm dbt-runtime-init }
}
finally { Pop-Location }

# 5. Create the source-aligned staging contract before loading data.
& "$PSScriptRoot\provision-warehouse.ps1" -Stage preload

Push-Location $projectRoot
try {
    # 6. Load the frozen baseline into PostgreSQL staging.
    Write-Host 'Loading source-aligned business staging...'
    Invoke-Checked -Description 'Initial business load' -Command {
        & docker compose run --rm --no-deps --entrypoint python airflow-init /opt/airflow/src/ingestion/initial_load.py --full
    }

    Write-Host 'Loading 5-minute telemetry aggregates...'
    Invoke-Checked -Description 'Initial telemetry load' -Command {
        & docker compose run --rm --no-deps --entrypoint python airflow-init /opt/airflow/src/ingestion/telemetry_load.py --full
    }

    # 7. Build the analytical warehouse from the reconciled staging layer.
    Write-Host 'Building dbt core warehouse...'
    Invoke-Checked -Description 'Initial dbt build' -Command {
        & docker compose run --rm --no-deps --entrypoint /home/airflow/.dbt-venv/bin/dbt airflow-init build --profiles-dir /opt/airflow/dbt --target-path /opt/airflow/dbt-runtime/target
    }
}
finally { Pop-Location }

# 8. Provision durable control, realtime, alert, quality, and serving objects.
& "$PSScriptRoot\provision-warehouse.ps1" -Stage postload

Push-Location $projectRoot
try {
    # 9. Start the complete runtime. The source simulator then advances whole-day
    #    source history from the frozen baseline while Airflow processes durable frontiers.
    Write-Host 'Starting full platform runtime...'
    Invoke-Checked -Description 'Full platform startup' -Command { & docker compose up -d }

    foreach ($service in @(
        'wwi-sqlserver',
        'warehouse-db',
        'airflow-db',
        'airflow-api-server',
        'airflow-scheduler',
        'airflow-dag-processor',
        'realtime-api',
        'realtime-consumer',
        'source-simulator'
    )) {
        Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service $service -TimeoutSeconds 420
    }

    # Fresh Airflow metadata starts DAGs paused by policy; make the repository
    # runtime match the validated portfolio operating state.
    foreach ($dag in @(
        'supply_chain_incremental_pipeline',
        'supply_chain_backfill',
        'supply_chain_quality_gate'
    )) {
        Invoke-Checked -Description "Unpause DAG '$dag'" -Command {
            & docker compose exec -T airflow-scheduler airflow dags unpause $dag
        }
    }

    Invoke-Checked -Description 'Airflow DAG import validation' -Command {
        & docker compose exec -T airflow-scheduler airflow dags list-import-errors
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'PLATFORM BOOTSTRAP PASS'
Write-Host 'Backend services are running. The Vite frontend is intentionally separate:'
Write-Host '  cd frontend'
Write-Host '  npm ci'
Write-Host '  npm run dev'
