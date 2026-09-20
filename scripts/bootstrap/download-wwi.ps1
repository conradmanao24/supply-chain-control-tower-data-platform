param([switch]$Force)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
$envFile = Join-Path $projectRoot '.env'
if (Test-Path $envFile) {
    Import-ProjectEnv -ProjectRoot $projectRoot
}

$defaultUrl = 'https://github.com/microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak'
$defaultFileName = 'WideWorldImporters-Full.bak'
$expectedBytes = 127111168
$expectedSha256 = 'E842BAD6CE02F74F166947E559DAB1B476EDD7EAAE3DA2AB9E3F522F1DD87124'
$expectedSignature = 'MSSQLBAK'

$url = [Environment]::GetEnvironmentVariable('WWI_BACKUP_URL', 'Process')
if ([string]::IsNullOrWhiteSpace($url)) { $url = $defaultUrl }

$fileName = [Environment]::GetEnvironmentVariable('WWI_BACKUP_FILENAME', 'Process')
if ([string]::IsNullOrWhiteSpace($fileName)) { $fileName = $defaultFileName }

$dataDir = Join-Path $projectRoot 'data\wwi'
$target = Join-Path $dataDir $fileName
$partial = "$target.partial"

function Assert-WwiArtifact {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path $Path)) {
        throw "WWI artifact does not exist: $Path"
    }

    $file = Get-Item $Path
    if ($file.Length -ne $expectedBytes) {
        throw "WWI artifact size mismatch. Expected $expectedBytes bytes, got $($file.Length)."
    }

    $stream = [System.IO.File]::OpenRead($file.FullName)
    try {
        $buffer = New-Object byte[] 8
        [void]$stream.Read($buffer, 0, 8)
        $signature = [System.Text.Encoding]::ASCII.GetString($buffer)
    }
    finally {
        $stream.Dispose()
    }

    if ($signature -ne $expectedSignature) {
        throw "WWI artifact header mismatch. Expected '$expectedSignature', got '$signature'."
    }

    $sha256 = (Get-FileHash -Algorithm SHA256 -Path $file.FullName).Hash
    if ($sha256 -ne $expectedSha256) {
        throw "WWI artifact SHA256 mismatch. Expected $expectedSha256, got $sha256."
    }

    return [pscustomobject]@{
        Path = $file.FullName
        Bytes = $file.Length
        SHA256 = $sha256
        Signature = $signature
    }
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if ((Test-Path $target) -and -not $Force) {
    $result = Assert-WwiArtifact -Path $target
    Write-Host 'WWI backup already exists and passed validation.'
    $result | Format-List
    exit 0
}

if (Test-Path $partial) {
    Remove-Item -Force $partial
}

Write-Host "Downloading official WideWorldImporters backup from: $url"
Invoke-WebRequest -Uri $url -OutFile $partial -MaximumRedirection 10

$result = Assert-WwiArtifact -Path $partial
Move-Item -Force $partial $target

Write-Host 'DOWNLOAD PASS'
Write-Host "PATH=$target"
Write-Host "BYTES=$($result.Bytes)"
Write-Host "SHA256=$($result.SHA256)"
Write-Host "SIGNATURE=$($result.Signature)"
