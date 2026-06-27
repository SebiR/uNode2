param(
    [string]$Fqbn = "esp8266:esp8266:generic:eesz=4M1M",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot "..")

$sketchDir =
    Join-Path $projectRoot "firmware\uNode_2"

$dataDir =
    Join-Path $sketchDir "data"

$arduinoCli =
    Join-Path $env:LOCALAPPDATA `
        "Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"

if (!(Test-Path $arduinoCli)) {
    throw "arduino-cli.exe not found at $arduinoCli"
}

$configHeader =
    Get-Content `
        -LiteralPath (Join-Path $sketchDir "config.h") `
        -Raw

function Get-FirmwareVersionPart {
    param(
        [string]$Name
    )

    $match =
        [regex]::Match(
            $configHeader,
            "#define\s+$Name\s+(\d+)")

    if (!$match.Success) {
        throw "$Name not found in config.h"
    }

    return $match.Groups[1].Value
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $encoding =
        New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        $encoding)
}

$version =
    "$(Get-FirmwareVersionPart "FW_VERSION_MAJOR").$(Get-FirmwareVersionPart "FW_VERSION_MINOR").$(Get-FirmwareVersionPart "FW_VERSION_PATCH")"

$configSchemaVersion =
    Get-FirmwareVersionPart "CONFIG_SCHEMA_VERSION"

$timestamp =
    Get-Date -Format "yyyyMMdd-HHmmss"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir =
        Join-Path $projectRoot "artifacts\release"
}

New-Item `
    -ItemType Directory `
    -Path $OutputDir `
    -Force |
    Out-Null

$buildPath =
    Join-Path ([System.IO.Path]::GetTempPath()) "unode-release-build"

if (Test-Path $buildPath) {
    Remove-Item `
        -LiteralPath $buildPath `
        -Recurse `
        -Force
}

Write-Host "Building firmware with FQBN $Fqbn"

& $arduinoCli `
    compile `
    --fqbn $Fqbn `
    --build-path $buildPath `
    $sketchDir

if ($LASTEXITCODE -ne 0) {
    throw "Firmware build failed"
}

$firmwareSource =
    Get-ChildItem `
        -Path $buildPath `
        -Filter "*.ino.bin" `
        -Recurse |
    Select-Object -First 1

if (!$firmwareSource) {
    throw "Firmware binary not found in $buildPath"
}

$artifactPrefix =
    "uNode-$version-$timestamp-4M1M"

$webVersionPath =
    Join-Path $dataDir "version.json"

$webVersionOriginalExists =
    Test-Path $webVersionPath

$webVersionOriginalBytes =
    if ($webVersionOriginalExists) {
        [System.IO.File]::ReadAllBytes($webVersionPath)
    } else {
        $null
    }

$webVersion = [ordered]@{
    project = "uNode"
    version = $version
    configSchemaVersion = [int]$configSchemaVersion
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
}

$webVersion |
    ConvertTo-Json -Depth 3 |
    ForEach-Object {
        Write-Utf8NoBom `
            -Path $webVersionPath `
            -Content $_
    }

$firmwareArtifact =
    Join-Path $OutputDir "$artifactPrefix-firmware.bin"

Copy-Item `
    -LiteralPath $firmwareSource.FullName `
    -Destination $firmwareArtifact `
    -Force

$mklittlefs =
    Get-ChildItem `
        -Path (Join-Path $env:LOCALAPPDATA "Arduino15\packages\esp8266") `
        -Recurse `
        -File `
        -Filter "mklittlefs.exe" |
    Select-Object -First 1

if (!$mklittlefs) {
    throw "mklittlefs.exe not found in the installed ESP8266 Arduino package"
}

$filesystemArtifact =
    Join-Path $OutputDir "$artifactPrefix-littlefs.bin"

Write-Host "Building LittleFS image"

try {
    & $mklittlefs.FullName `
        -c $dataDir `
        -b 8192 `
        -p 256 `
        -s 1024000 `
        $filesystemArtifact

    if ($LASTEXITCODE -ne 0) {
        throw "LittleFS image build failed"
    }
} finally {
    if ($webVersionOriginalExists) {
        [System.IO.File]::WriteAllBytes(
            $webVersionPath,
            $webVersionOriginalBytes)
    } else {
        Remove-Item `
            -LiteralPath $webVersionPath `
            -ErrorAction SilentlyContinue
    }
}

$firmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $firmwareArtifact

$filesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $filesystemArtifact

$manifest = [ordered]@{
    project = "uNode"
    version = $version
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    fqbn = $Fqbn
    flashLayout = "4M1M"
    littleFs = [ordered]@{
        size = 1024000
        blockSize = 8192
        pageSize = 256
        file = (Split-Path $filesystemArtifact -Leaf)
        sha256 = $filesystemHash.Hash
    }
    firmware = [ordered]@{
        file = (Split-Path $firmwareArtifact -Leaf)
        size = (Get-Item $firmwareArtifact).Length
        sha256 = $firmwareHash.Hash
    }
}

$manifestPath =
    Join-Path $OutputDir "$artifactPrefix-manifest.json"

$manifest |
    ConvertTo-Json -Depth 5 |
    ForEach-Object {
        Write-Utf8NoBom `
            -Path $manifestPath `
            -Content $_
    }

Write-Host ""
Write-Host "Artifacts written to $OutputDir"
Write-Host "Firmware : $firmwareArtifact"
Write-Host "LittleFS : $filesystemArtifact"
Write-Host "Manifest : $manifestPath"
