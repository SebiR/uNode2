param(
    [string]$Port = "",
    [int]$Baud = 115200,
    [string]$Output = "logs\unode-serial.log",
    [switch]$List
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )

Set-Location $projectRoot

$argsList = @("tools\serial_capture.py")

if ($List)
{
    $argsList += "--list"
}
else
{
    if ($Port.Length -eq 0)
    {
        throw "Set -Port COMx or use -List to show serial ports."
    }

    $argsList += "--port"
    $argsList += $Port
    $argsList += "--baud"
    $argsList += "$Baud"
    $argsList += "--output"
    $argsList += $Output
}

python @argsList
