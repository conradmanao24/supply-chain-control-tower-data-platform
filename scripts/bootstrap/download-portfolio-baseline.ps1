param(
    [switch]$Force,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\lib.ps1"

$projectRoot = Get-ProjectRoot
$envFile = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    Import-ProjectEnv -ProjectRoot $projectRoot
}

$defaultRelativeFile = 'full-master/wwi-full-master-2026-09-15.bak'
$defaultAssetName = 'wwi-full-master-2026-09-15.bak'
$defaultReleaseTag = 'v1.0-data-baseline'
$defaultUrl = "https://github.com/conradmanao24/supply-chain-control-tower-data-platform/releases/download/$defaultReleaseTag/$defaultAssetName"
$defaultBytes = [int64]1662111744
$defaultSha256 = '1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30'
$expectedSignature = 'MSSQLBAK'

$relativeFile = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_FILENAME)) { $defaultRelativeFile } else { $env:WWI_BASELINE_FILENAME }
$url = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_URL)) { $defaultUrl } else { $env:WWI_BASELINE_URL }
$expectedBytes = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_SIZE_BYTES)) { $defaultBytes } else { [int64]$env:WWI_BASELINE_SIZE_BYTES }
$expectedSha256 = if ([string]::IsNullOrWhiteSpace($env:WWI_BASELINE_SHA256)) { $defaultSha256 } else { $env:WWI_BASELINE_SHA256.ToUpperInvariant() }

$target = Join-Path (Join-Path $projectRoot 'data\baselines') ($relativeFile -replace '/', '\')
$targetDir = Split-Path -Parent $target
$partial = "$target.partial"

function Assert-PortfolioBaseline {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Portfolio baseline does not exist: $Path"
    }

    $file = Get-Item -LiteralPath $Path
    if ($file.Length -ne $expectedBytes) {
        throw "Portfolio baseline size mismatch. Expected $expectedBytes bytes, got $($file.Length)."
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
        throw "Portfolio baseline header mismatch. Expected '$expectedSignature', got '$signature'."
    }

    $sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($sha256 -ne $expectedSha256) {
        throw "Portfolio baseline SHA-256 mismatch. Expected $expectedSha256, got $sha256."
    }

    return [pscustomobject]@{
        Path = $file.FullName
        Bytes = $file.Length
        SHA256 = $sha256
        Signature = $signature
    }
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

if ((Test-Path -LiteralPath $target) -and -not $Force) {
    $result = Assert-PortfolioBaseline -Path $target
    Write-Host 'Portfolio baseline already exists and passed validation.'
    $result | Format-List
    exit 0
}

if ($ValidateOnly) {
    throw "ValidateOnly was requested but no valid baseline exists at: $target"
}

if ($Force -and (Test-Path -LiteralPath $target)) {
    Remove-Item -LiteralPath $target -Force
}

Write-Host "Downloading frozen 2026 portfolio baseline from:"
Write-Host "  $url"
Write-Host "Target:"
Write-Host "  $target"
Write-Host ''
$expectedGiB = [math]::Round($expectedBytes / 1GB, 3)
Write-Host "Expected download size: $expectedGiB GiB ($expectedBytes bytes)."

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($null -ne $curl) {
    $curlArgs = @(
        '--location',
        '--fail',
        '--retry', '3',
        '--retry-delay', '2',
        '--output', $partial,
        $url
    )

    if (Test-Path -LiteralPath $partial) {
        Write-Host 'A partial file exists; attempting to resume it.'
        $curlArgs = @(
            '--location',
            '--fail',
            '--retry', '3',
            '--retry-delay', '2',
            '--continue-at', '-',
            '--output', $partial,
            $url
        )
    }

    & $curl.Source @curlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Baseline download failed with curl exit code $LASTEXITCODE."
    }
}
else {
    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial -Force
    }
    $previousProgressPreference = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $url -OutFile $partial -MaximumRedirection 10
    }
    finally {
        $ProgressPreference = $previousProgressPreference
    }
}

$result = Assert-PortfolioBaseline -Path $partial
Move-Item -LiteralPath $partial -Destination $target -Force

Write-Host ''
Write-Host 'PORTFOLIO BASELINE DOWNLOAD PASS'
Write-Host "PATH=$target"
Write-Host "BYTES=$($result.Bytes)"
Write-Host "SHA256=$($result.SHA256)"
Write-Host "SIGNATURE=$($result.Signature)"
