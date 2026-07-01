param(
    [string]$Report = "",
    [string]$OutputDir = "",
    [switch]$HtmlOnly
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )

Set-Location $projectRoot

$argsList = @()

if ($Report.Length -gt 0)
{
    $argsList += $Report
}

if ($OutputDir.Length -gt 0)
{
    $argsList += "--output-dir"
    $argsList += $OutputDir
}

if ($HtmlOnly)
{
    $argsList += "--html-only"
}

python .\tools\generate_certificate.py @argsList
