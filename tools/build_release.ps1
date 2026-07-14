param(
    [string]$Fqbn = "esp8266:esp8266:generic:eesz=4M1M",
    [string]$OutputDir = "",
    [switch]$IncludeTestHarness
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot "..")

$sketchDir =
    Join-Path $projectRoot "firmware\uNode_2"

$librariesDir =
    Join-Path $projectRoot "libraries"

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
        "--libraries",
        $librariesDir,
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

    foreach ($extension in @("elf", "map")) {
        $debugSource =
            Get-ChildItem `
                -Path $buildPath `
                -Filter "*.ino.$extension" `
                -Recurse |
            Select-Object -First 1

        if (!$debugSource) {
            throw "$Profile firmware $extension file not found in $buildPath"
        }

        $debugArtifact =
            Join-Path $OutputDir "uNode-$version$Suffix-firmware.$extension"

        Copy-Item `
            -LiteralPath $debugSource.FullName `
            -Destination $debugArtifact `
            -Force
    }

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

$testFirmwareArtifact = $null
$legacyTestFirmwareArtifact = $null

if ($IncludeTestHarness) {
    $testFirmwareArtifact =
        Build-FirmwareArtifact `
            -Profile "test" `
            -Suffix "_test" `
            -BuildProperties @(
                "compiler.cpp.extra_flags=-DENABLE_TEST_HARNESS_API=1"
            )

    $legacyTestFirmwareArtifact =
        Build-FirmwareArtifact `
            -Profile "legacy-test" `
            -Suffix "_legacy_test" `
            -BuildProperties @(
                "compiler.cpp.extra_flags=-DUSE_LEGACY_HARDWARE=1 -DENABLE_TEST_HARNESS_API=1"
            )
}

$firmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version-firmware.elf"
$firmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version-firmware.map"
$legacyFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-firmware.elf"
$legacyFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-firmware.map"
$testFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_test-firmware.elf"
$testFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_test-firmware.map"
$legacyTestFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy_test-firmware.elf"
$legacyTestFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy_test-firmware.map"

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

$firmwareElfHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $firmwareElfArtifact
$firmwareMapHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $firmwareMapArtifact
$legacyFirmwareElfHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $legacyFirmwareElfArtifact
$legacyFirmwareMapHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $legacyFirmwareMapArtifact

$filesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $filesystemArtifact

$legacyFilesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $legacyFilesystemArtifact

if ($IncludeTestHarness) {
    $testFirmwareHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $testFirmwareArtifact
    $legacyTestFirmwareHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $legacyTestFirmwareArtifact
    $testFirmwareElfHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $testFirmwareElfArtifact
    $testFirmwareMapHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $testFirmwareMapArtifact
    $legacyTestFirmwareElfHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $legacyTestFirmwareElfArtifact
    $legacyTestFirmwareMapHash =
        Get-FileHash -Algorithm SHA256 -LiteralPath $legacyTestFirmwareMapArtifact
}

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
            debug = [ordered]@{
                elf = [ordered]@{
                    file = (Split-Path $firmwareElfArtifact -Leaf)
                    size = (Get-Item $firmwareElfArtifact).Length
                    sha256 = $firmwareElfHash.Hash
                }
                map = [ordered]@{
                    file = (Split-Path $firmwareMapArtifact -Leaf)
                    size = (Get-Item $firmwareMapArtifact).Length
                    sha256 = $firmwareMapHash.Hash
                }
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
            debug = [ordered]@{
                elf = [ordered]@{
                    file = (Split-Path $legacyFirmwareElfArtifact -Leaf)
                    size = (Get-Item $legacyFirmwareElfArtifact).Length
                    sha256 = $legacyFirmwareElfHash.Hash
                }
                map = [ordered]@{
                    file = (Split-Path $legacyFirmwareMapArtifact -Leaf)
                    size = (Get-Item $legacyFirmwareMapArtifact).Length
                    sha256 = $legacyFirmwareMapHash.Hash
                }
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

if ($IncludeTestHarness) {
    $manifest["profiles"]["test"] = [ordered]@{
        hardwareProfile = "normal"
        testHarnessApi = $true
        buildProperties = @(
            "compiler.cpp.extra_flags=-DENABLE_TEST_HARNESS_API=1"
        )
        firmware = [ordered]@{
            file = (Split-Path $testFirmwareArtifact -Leaf)
            size = (Get-Item $testFirmwareArtifact).Length
            sha256 = $testFirmwareHash.Hash
        }
        debug = [ordered]@{
            elf = [ordered]@{
                file = (Split-Path $testFirmwareElfArtifact -Leaf)
                size = (Get-Item $testFirmwareElfArtifact).Length
                sha256 = $testFirmwareElfHash.Hash
            }
            map = [ordered]@{
                file = (Split-Path $testFirmwareMapArtifact -Leaf)
                size = (Get-Item $testFirmwareMapArtifact).Length
                sha256 = $testFirmwareMapHash.Hash
            }
        }
        littleFs = $manifest["profiles"]["normal"]["littleFs"]
    }

    $manifest["profiles"]["legacyTest"] = [ordered]@{
        hardwareProfile = "legacy"
        testHarnessApi = $true
        buildProperties = @(
            "compiler.cpp.extra_flags=-DUSE_LEGACY_HARDWARE=1 -DENABLE_TEST_HARNESS_API=1"
        )
        firmware = [ordered]@{
            file = (Split-Path $legacyTestFirmwareArtifact -Leaf)
            size = (Get-Item $legacyTestFirmwareArtifact).Length
            sha256 = $legacyTestFirmwareHash.Hash
        }
        debug = [ordered]@{
            elf = [ordered]@{
                file = (Split-Path $legacyTestFirmwareElfArtifact -Leaf)
                size = (Get-Item $legacyTestFirmwareElfArtifact).Length
                sha256 = $legacyTestFirmwareElfHash.Hash
            }
            map = [ordered]@{
                file = (Split-Path $legacyTestFirmwareMapArtifact -Leaf)
                size = (Get-Item $legacyTestFirmwareMapArtifact).Length
                sha256 = $legacyTestFirmwareMapHash.Hash
            }
        }
        littleFs = $manifest["profiles"]["legacy"]["littleFs"]
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
Write-Host "Debug normal    : $firmwareElfArtifact / $firmwareMapArtifact"
Write-Host "LittleFS normal : $filesystemArtifact"
Write-Host "Firmware legacy : $legacyFirmwareArtifact"
Write-Host "Debug legacy    : $legacyFirmwareElfArtifact / $legacyFirmwareMapArtifact"
Write-Host "LittleFS legacy : $legacyFilesystemArtifact"
if ($IncludeTestHarness) {
    Write-Host "Firmware test   : $testFirmwareArtifact"
    Write-Host "Firmware legacy test: $legacyTestFirmwareArtifact"
}
Write-Host "Manifest        : $manifestPath"
