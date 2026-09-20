. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
Import-ProjectEnv -ProjectRoot $projectRoot
Assert-DockerRuntimeAvailable
Assert-LocalPasswordConfigured

$port = [int](Require-EnvValue -Name 'MSSQL_HOST_PORT')
Assert-SqlHostPortAvailable -ProjectRoot $projectRoot -Port $port

Write-Host "PRECHECK PASS: Docker is available, Docker Engine is running, credentials are configured, and host port $port is available for this project."
