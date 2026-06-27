param(
    [switch]$Integration,
    [string]$NodeIp = "2.0.0.1",
    [string]$BaseUrl = "",
    [string]$Password = "",
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

    if ($Path.Length -eq 0)
    {
        $Path = "tests/integration"
    }

    $pytestArgs = @("-s", "-vv", $Path)

    Write-Host "Mode    : integration" -ForegroundColor Yellow
    Write-Host "Node IP : $env:UNODE_IP"
    Write-Host "Base URL: $env:UNODE_BASE_URL"
}
else
{
    Remove-Item Env:\UNODE_RUN_INTEGRATION -ErrorAction SilentlyContinue

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
exit $LASTEXITCODE
