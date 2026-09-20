. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
$database = Require-EnvValue -Name 'WWI_DATABASE'
$saPassword = Require-EnvValue -Name 'MSSQL_SA_PASSWORD'

Push-Location $projectRoot
try {
    $sqlcmd = $null
    foreach ($candidate in @('/opt/mssql-tools18/bin/sqlcmd', '/opt/mssql-tools/bin/sqlcmd')) {
        & docker compose exec -T wwi-sqlserver test -x $candidate *> $null
        if ($LASTEXITCODE -eq 0) {
            $sqlcmd = $candidate
            break
        }
    }

    if (-not $sqlcmd) {
        throw 'sqlcmd was not found inside the SQL Server container.'
    }

    Invoke-Checked -Description 'WWI validation' -Command {
        & docker compose exec -T wwi-sqlserver $sqlcmd `
            -S localhost `
            -U sa `
            -P $saPassword `
            -C `
            -b `
            -i /opt/project/sql/bootstrap/validate_wwi.sql `
            -v "DatabaseName=$database"
    }
}
finally {
    Pop-Location
}

Write-Host 'SOURCE VALIDATION PASS'
