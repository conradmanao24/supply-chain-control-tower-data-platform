param()

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
Assert-DockerRuntimeAvailable
Assert-LocalPasswordConfigured

$database = Require-EnvValue -Name 'WWI_DATABASE'
$saPassword = Require-EnvValue -Name 'MSSQL_SA_PASSWORD'
$baselineFile = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_FILENAME)) { 'full-master/wwi-full-master-2026-09-15.bak' } else { $env:WWI_BASELINE_FILENAME }
$expectedSize = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_SIZE_BYTES)) { [int64]1662111744 } else { [int64]$env:WWI_BASELINE_SIZE_BYTES }
$expectedHash = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_SHA256)) { '1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30' } else { $env:WWI_BASELINE_SHA256.ToUpperInvariant() }

$localPath = Join-Path (Join-Path $projectRoot 'data\baselines') ($baselineFile -replace '/', '\')
if (-not (Test-Path -LiteralPath $localPath)) {
    Write-Host 'Frozen portfolio baseline is not present locally.'
    Write-Host 'Downloading the checksum-pinned 2026 baseline from the project GitHub Release...'
    & "$PSScriptRoot\download-portfolio-baseline.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Portfolio baseline download failed with exit code $LASTEXITCODE."
    }
}

$file = Get-Item -LiteralPath $localPath
if ($file.Length -ne $expectedSize) { throw "Baseline size mismatch: expected $expectedSize bytes, found $($file.Length)." }

$actualHash = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) { throw "Baseline SHA-256 mismatch: expected $expectedHash, found $actualHash." }

Push-Location $projectRoot
try {
    Invoke-Checked -Description 'Starting SQL Server' -Command { & docker compose up -d wwi-sqlserver }
    Wait-ComposeServiceReady -ProjectRoot $projectRoot -Service 'wwi-sqlserver' -TimeoutSeconds 300
    $sqlcmd = Get-SqlCmdPath -ProjectRoot $projectRoot
    $containerPath = '/var/opt/mssql/baselines/' + $baselineFile.Replace('\', '/')
    Invoke-Checked -Description 'Frozen baseline restore' -Command {
        & docker compose exec -T wwi-sqlserver $sqlcmd -S localhost -U sa -P $saPassword -C -b -i /opt/project/sql/bootstrap/restore_wwi.sql -v "DatabaseName=$database" "BackupPath=$containerPath"
    }
}
finally { Pop-Location }

& "$PSScriptRoot\validate-source.ps1"
if ($LASTEXITCODE -ne 0) { throw "Source validation failed with exit code $LASTEXITCODE." }

Write-Host 'PORTFOLIO BASELINE RESTORE PASS'
