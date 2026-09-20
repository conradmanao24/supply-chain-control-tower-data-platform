Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Import-ProjectEnv {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $envFile = Join-Path $ProjectRoot '.env'
    if (-not (Test-Path $envFile)) {
        throw "Missing .env. Copy .env.example to .env and set a local MSSQL_SA_PASSWORD before runtime."
    }

    foreach ($rawLine in Get-Content $envFile) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }

        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { continue }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")

        if (-not (Test-Path "Env:$key")) {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

function Require-EnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment value '$Name' is missing."
    }
    return $value
}

function Assert-DockerRuntimeAvailable {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI was not found in PATH.'
    }

    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose is not available.'
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Engine is not running. Start Docker yourself, then rerun the bootstrap. This project never starts Docker Desktop automatically.'
    }
}

function Get-ActiveTcpPorts {
    return [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners().Port
}

function Test-ProjectOwnsSqlPort {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][int]$Port
    )

    Push-Location $ProjectRoot
    try {
        $containerId = (& docker compose ps -q wwi-sqlserver 2>$null | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace($containerId)) { return $false }

        $published = (& docker port $containerId 1433/tcp 2>$null)
        if ($LASTEXITCODE -ne 0) { return $false }

        return [bool]($published -match ":$Port$")
    }
    finally {
        Pop-Location
    }
}

function Assert-SqlHostPortAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $inUse = (Get-ActiveTcpPorts) -contains $Port
    if (-not $inUse) { return }

    if (Test-ProjectOwnsSqlPort -ProjectRoot $ProjectRoot -Port $Port) { return }

    throw "Host port $Port is already in use by another process or project. Choose another MSSQL_HOST_PORT in .env before starting the source."
}

function Assert-LocalPasswordConfigured {
    $password = Require-EnvValue -Name 'MSSQL_SA_PASSWORD'
    if ($password -eq 'CHANGE_ME_WITH_A_STRONG_LOCAL_PASSWORD') {
        throw 'MSSQL_SA_PASSWORD still contains the placeholder value. Set a strong local password in .env.'
    }
    if ($password.Length -lt 8) {
        throw 'MSSQL_SA_PASSWORD must be at least 8 characters. SQL Server may enforce additional complexity requirements.'
    }
}


function Wait-ComposeServiceReady {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$Service,
        [int]$TimeoutSeconds = 300
    )

    Push-Location $ProjectRoot
    try {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        do {
            $containerId = (& docker compose ps -q $Service 2>$null | Select-Object -First 1)
            if (-not [string]::IsNullOrWhiteSpace($containerId)) {
                $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId 2>$null).Trim()
                if ($state -in @('healthy', 'running')) {
                    return
                }
                if ($state -in @('unhealthy', 'exited', 'dead')) {
                    throw "Service '$Service' entered state '$state'."
                }
            }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
    }
    finally {
        Pop-Location
    }

    throw "Timed out waiting for service '$Service' to become ready."
}

function Get-SqlCmdPath {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    Push-Location $ProjectRoot
    try {
        foreach ($candidate in @('/opt/mssql-tools18/bin/sqlcmd', '/opt/mssql-tools/bin/sqlcmd')) {
            & docker compose exec -T wwi-sqlserver test -x $candidate *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
    }
    finally {
        Pop-Location
    }

    throw 'sqlcmd was not found inside the SQL Server container.'
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$Description
    )

    # Docker/sqlcmd/psql write normal progress and informational output to
    # stderr. Under Windows PowerShell with ErrorActionPreference=Stop those
    # records can become terminating errors even when the native process exits
    # successfully. Native command success is therefore decided by exit code.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Command
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($nativeExitCode -ne 0) {
        throw "$Description failed with exit code $nativeExitCode."
    }
}

function Assert-PlatformSecretsConfigured {
    $required = @(
        'MSSQL_SA_PASSWORD',
        'DWH_PASSWORD',
        'AIRFLOW_DB_PASSWORD',
        'AIRFLOW_FERNET_KEY',
        'AIRFLOW_API_SECRET_KEY',
        'AIRFLOW_JWT_SECRET',
        'WWI_SOURCE_PASSWORD',
        'WWI_EVENT_PASSWORD'
    )

    foreach ($name in $required) {
        $value = Require-EnvValue -Name $name
        if ($value -match '^(CHANGE_ME|GENERATE_A_VALID)') {
            throw "Environment value '$name' still contains a placeholder. Update .env before platform bootstrap."
        }
    }
}
