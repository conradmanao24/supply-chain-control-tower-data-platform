. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot

& "$PSScriptRoot\preflight-source.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& "$PSScriptRoot\download-wwi.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location $projectRoot
try {
    Write-Host 'Starting WWI SQL Server service...'
    Invoke-Checked -Description 'WWI SQL Server startup' -Command {
        & docker compose up -d wwi-sqlserver
    }

    $containerId = (& docker compose ps -q wwi-sqlserver | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw 'WWI SQL Server container was not created.'
    }

    $deadline = (Get-Date).AddMinutes(5)
    do {
        $health = (& docker inspect --format '{{.State.Health.Status}}' $containerId 2>$null).Trim()
        if ($health -eq 'healthy') { break }
        if ($health -eq 'unhealthy') { throw 'WWI SQL Server container became unhealthy.' }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    if ($health -ne 'healthy') {
        throw 'Timed out waiting for WWI SQL Server health check.'
    }
}
finally {
    Pop-Location
}

& "$PSScriptRoot\restore-wwi.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& "$PSScriptRoot\validate-source.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'SOURCE SOURCE BOOTSTRAP PASS'
