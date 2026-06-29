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

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir =
        Join-Path $projectRoot "artifacts\release"
}

New-Item `
    -ItemType Directory `
    -Path $OutputDir `
    -Force |
    Out-Null

function Build-FirmwareArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Profile,

        [string]$Suffix = "",

        [string[]]$BuildProperties = @()
    )

    $buildPath =
        Join-Path ([System.IO.Path]::GetTempPath()) "unode-release-build-$Profile"

    if (Test-Path $buildPath) {
        Remove-Item `
            -LiteralPath $buildPath `
            -Recurse `
            -Force
    }

    Write-Host "Building $Profile firmware with FQBN $Fqbn"

    $compileArgs = @(
        "compile",
        "--fqbn",
        $Fqbn,
        "--build-path",
        $buildPath
    )

    foreach ($property in $BuildProperties) {
        $compileArgs += @(
            "--build-property",
            $property
        )
    }

    $compileArgs += $sketchDir

    & $arduinoCli @compileArgs

    if ($LASTEXITCODE -ne 0) {
        throw "$Profile firmware build failed"
    }

    $firmwareSource =
        Get-ChildItem `
            -Path $buildPath `
            -Filter "*.ino.bin" `
            -Recurse |
        Select-Object -First 1

    if (!$firmwareSource) {
        throw "$Profile firmware binary not found in $buildPath"
    }

    $artifact =
        Join-Path $OutputDir "uNode-$version$Suffix-firmware.bin"

    Copy-Item `
        -LiteralPath $firmwareSource.FullName `
        -Destination $artifact `
        -Force

    return $artifact
}

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

$firmwareArtifact =
    Build-FirmwareArtifact `
        -Profile "normal" `
        -Suffix ""

$legacyFirmwareArtifact =
    Build-FirmwareArtifact `
        -Profile "legacy" `
        -Suffix "_legacy" `
        -BuildProperties @(
            "compiler.cpp.extra_flags=-DUSE_LEGACY_HARDWARE=1"
        )

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
    Join-Path $OutputDir "uNode-$version-littlefs.bin"

$legacyFilesystemArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-littlefs.bin"

Write-Host "Building LittleFS image"

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

Copy-Item `
    -LiteralPath $filesystemArtifact `
    -Destination $legacyFilesystemArtifact `
    -Force

$firmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $firmwareArtifact

$legacyFirmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $legacyFirmwareArtifact

$filesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $filesystemArtifact

$legacyFilesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $legacyFilesystemArtifact

$manifest = [ordered]@{
    project = "uNode"
    version = $version
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    fqbn = $Fqbn
    flashLayout = "4M1M"
    profiles = [ordered]@{
        normal = [ordered]@{
            hardwareProfile = "normal"
            buildProperties = @()
            firmware = [ordered]@{
                file = (Split-Path $firmwareArtifact -Leaf)
                size = (Get-Item $firmwareArtifact).Length
                sha256 = $firmwareHash.Hash
            }
            littleFs = [ordered]@{
                size = 1024000
                blockSize = 8192
                pageSize = 256
                file = (Split-Path $filesystemArtifact -Leaf)
                sha256 = $filesystemHash.Hash
            }
        }
        legacy = [ordered]@{
            hardwareProfile = "legacy"
            buildProperties = @(
                "compiler.cpp.extra_flags=-DUSE_LEGACY_HARDWARE=1"
            )
            firmware = [ordered]@{
                file = (Split-Path $legacyFirmwareArtifact -Leaf)
                size = (Get-Item $legacyFirmwareArtifact).Length
                sha256 = $legacyFirmwareHash.Hash
            }
            littleFs = [ordered]@{
                size = 1024000
                blockSize = 8192
                pageSize = 256
                file = (Split-Path $legacyFilesystemArtifact -Leaf)
                sha256 = $legacyFilesystemHash.Hash
            }
        }
    }
}

$manifestPath =
    Join-Path $OutputDir "uNode-$version-manifest.json"

$manifest |
    ConvertTo-Json -Depth 5 |
    ForEach-Object {
        Write-Utf8NoBom `
            -Path $manifestPath `
            -Content $_
    }

Write-Host ""
Write-Host "Artifacts written to $OutputDir"
Write-Host "Firmware normal : $firmwareArtifact"
Write-Host "LittleFS normal : $filesystemArtifact"
Write-Host "Firmware legacy : $legacyFirmwareArtifact"
Write-Host "LittleFS legacy : $legacyFilesystemArtifact"
Write-Host "Manifest        : $manifestPath"
