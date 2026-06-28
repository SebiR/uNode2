param(
    [switch]$Integration,
    [string]$NodeIp = "2.0.0.1",
    [string]$BaseUrl = "",
    [string]$Password = "",
    [string]$Rp2040Port = "",
    [int]$SoakSeconds = 0,
    [int]$DmxSoakSeconds = 0,
    [double]$SoakInterval = 0,
    [double]$SoakGrace = 0,
    [string]$Path = ""
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )

Set-Location $projectRoot

if ($BaseUrl.Length -eq 0)
{
    $BaseUrl = "http://$NodeIp"
}

Write-Host "uNode test runner" -ForegroundColor Cyan
Write-Host "Project : $projectRoot"
Write-Host "Python  : " -NoNewline
python --version
Write-Host "pytest  : " -NoNewline
python -m pytest --version

if ($Integration)
{
    $env:UNODE_RUN_INTEGRATION = "1"
    $env:UNODE_IP = $NodeIp
    $env:UNODE_BASE_URL = $BaseUrl

    if ($Password.Length -gt 0)
    {
        $env:UNODE_PASSWORD = $Password
    }

    if ($Rp2040Port.Length -gt 0)
    {
        $env:UNODE_RP2040_PORT = $Rp2040Port
    }
    else
    {
        Remove-Item Env:\UNODE_RP2040_PORT -ErrorAction SilentlyContinue
    }

    if ($SoakSeconds -gt 0)
    {
        $env:UNODE_SOAK_SECONDS = "$SoakSeconds"
    }

    if ($DmxSoakSeconds -gt 0)
    {
        $env:UNODE_DMX_SOAK_SECONDS = "$DmxSoakSeconds"
    }

    if ($SoakInterval -gt 0)
    {
        $env:UNODE_SOAK_INTERVAL = "$SoakInterval"
    }

    if ($SoakGrace -gt 0)
    {
        $env:UNODE_SOAK_REACHABILITY_GRACE = "$SoakGrace"
    }

    if ($Path.Length -eq 0)
    {
        $Path = "tests/integration"
    }

    $pytestArgs = @("-s", "-vv", $Path)

    Write-Host "Mode    : integration" -ForegroundColor Yellow
    Write-Host "Node IP : $env:UNODE_IP"
    Write-Host "Base URL: $env:UNODE_BASE_URL"
    if ($env:UNODE_RP2040_PORT)
    {
        Write-Host "RP2040  : $env:UNODE_RP2040_PORT"
    }
    if ($env:UNODE_SOAK_SECONDS)
    {
        Write-Host "Soak    : $env:UNODE_SOAK_SECONDS seconds"
    }
    if ($env:UNODE_DMX_SOAK_SECONDS)
    {
        Write-Host "DMX Soak: $env:UNODE_DMX_SOAK_SECONDS seconds"
    }
}
else
{
    Remove-Item Env:\UNODE_RUN_INTEGRATION -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DMX_SOAK_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_INTERVAL -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_REACHABILITY_GRACE -ErrorAction SilentlyContinue

    if ($Path.Length -eq 0)
    {
        $Path = "tests/unit"
    }

    $pytestArgs = @($Path)

    Write-Host "Mode    : unit/offline" -ForegroundColor Green
}

Write-Host "Tests   : $Path"
if ($Integration)
{
    Write-Host "Output  : verbose integration progress"
}
Write-Host ""

python -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Cleaning pytest caches" -ForegroundColor DarkGray
$cacheDirs =
    Get-ChildItem `
        -Path $projectRoot `
        -Recurse `
        -Directory `
        -Force `
        -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "__pycache__" -or
        $_.Name -eq ".pytest_cache"
    } |
    Sort-Object {
        $_.FullName.Length
    } -Descending

foreach ($cacheDir in $cacheDirs)
{
    Remove-Item `
        -LiteralPath $cacheDir.FullName `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

exit $exitCode
