param(
    [string]$OutputDir = "",
    [switch]$IncludeTestHarness,
    [string]$PlatformIoExecutable = ""
)

$ErrorActionPreference = "Stop"

$sketchDir =
    Resolve-Path (
        Join-Path $PSScriptRoot "..")

$projectRoot =
    Resolve-Path (
        Join-Path $sketchDir "..\..")

$dataDir =
    Join-Path $sketchDir "data"

function Resolve-PlatformIoExecutable {
    if (![string]::IsNullOrWhiteSpace($PlatformIoExecutable)) {
        if (!(Test-Path -LiteralPath $PlatformIoExecutable)) {
            throw "PlatformIO executable not found at $PlatformIoExecutable"
        }

        return (Resolve-Path -LiteralPath $PlatformIoExecutable).Path
    }

    foreach ($commandName in @("pio", "platformio")) {
        $command =
            Get-Command $commandName -ErrorAction SilentlyContinue

        if ($command) {
            return $command.Source
        }
    }

    $homeDirectory =
        [Environment]::GetFolderPath("UserProfile")

    foreach ($candidate in @(
        (Join-Path $homeDirectory ".platformio\penv\Scripts\pio.exe"),
        (Join-Path $homeDirectory ".platformio\penv\bin\pio")
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "PlatformIO Core not found. Install the PlatformIO IDE extension or PlatformIO Core 6.1.19."
}

$platformIo =
    Resolve-PlatformIoExecutable

$platformIoVersion =
    (& $platformIo --version).Trim()

if ($LASTEXITCODE -ne 0) {
    throw "Failed to execute PlatformIO Core at $platformIo"
}

$buildRoot =
    Join-Path $sketchDir ".pio\build"

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

        [string]$Suffix = ""
    )

    $buildPath =
        Join-Path $buildRoot $Profile

    Write-Host "Building PlatformIO environment $Profile"

    & $platformIo run --project-dir $sketchDir -e $Profile -t clean |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "$Profile environment clean failed"
    }

    & $platformIo run --project-dir $sketchDir -e $Profile |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "$Profile firmware build failed"
    }

    $firmwareSource =
        Join-Path $buildPath "firmware.bin"

    if (!(Test-Path -LiteralPath $firmwareSource)) {
        throw "$Profile firmware binary not found in $buildPath"
    }

    $artifact =
        Join-Path $OutputDir "uNode-$version$Suffix-firmware.bin"

    Copy-Item `
        -LiteralPath $firmwareSource `
        -Destination $artifact `
        -Force

    foreach ($extension in @("elf", "map")) {
        $debugSource =
            Join-Path $buildPath "firmware.$extension"

        if (!(Test-Path -LiteralPath $debugSource)) {
            throw "$Profile firmware $extension file not found in $buildPath"
        }

        $debugArtifact =
            Join-Path $OutputDir "uNode-$version$Suffix-firmware.$extension"

        Copy-Item `
            -LiteralPath $debugSource `
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
        -Suffix "_legacy"

$gpioFixFirmwareArtifact =
    Build-FirmwareArtifact `
        -Profile "gpio_fix" `
        -Suffix "_gpio_fix"

$testFirmwareArtifact = $null
$legacyTestFirmwareArtifact = $null

if ($IncludeTestHarness) {
    $testFirmwareArtifact =
        Build-FirmwareArtifact `
            -Profile "test" `
            -Suffix "_test"

    $legacyTestFirmwareArtifact =
        Build-FirmwareArtifact `
            -Profile "legacy_test" `
            -Suffix "_legacy_test"
}

$firmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version-firmware.elf"
$firmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version-firmware.map"
$legacyFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-firmware.elf"
$legacyFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-firmware.map"
$gpioFixFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_gpio_fix-firmware.elf"
$gpioFixFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_gpio_fix-firmware.map"
$testFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_test-firmware.elf"
$testFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_test-firmware.map"
$legacyTestFirmwareElfArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy_test-firmware.elf"
$legacyTestFirmwareMapArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy_test-firmware.map"

$filesystemArtifact =
    Join-Path $OutputDir "uNode-$version-littlefs.bin"

$legacyFilesystemArtifact =
    Join-Path $OutputDir "uNode-$version`_legacy-littlefs.bin"

$gpioFixFilesystemArtifact =
    Join-Path $OutputDir "uNode-$version`_gpio_fix-littlefs.bin"

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
    & $platformIo run --project-dir $sketchDir -e normal -t buildfs

    if ($LASTEXITCODE -ne 0) {
        throw "LittleFS image build failed"
    }

    $filesystemSource =
        Join-Path $buildRoot "normal\littlefs.bin"

    if (!(Test-Path -LiteralPath $filesystemSource)) {
        throw "PlatformIO LittleFS image not found at $filesystemSource"
    }

    if ((Get-Item -LiteralPath $filesystemSource).Length -ne 1024000) {
        throw "PlatformIO LittleFS image does not match the 4M1M layout"
    }

    Copy-Item `
        -LiteralPath $filesystemSource `
        -Destination $filesystemArtifact `
        -Force
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

Copy-Item `
    -LiteralPath $filesystemArtifact `
    -Destination $gpioFixFilesystemArtifact `
    -Force

$firmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $firmwareArtifact

$legacyFirmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $legacyFirmwareArtifact

$gpioFixFirmwareHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $gpioFixFirmwareArtifact

$firmwareElfHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $firmwareElfArtifact
$firmwareMapHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $firmwareMapArtifact
$legacyFirmwareElfHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $legacyFirmwareElfArtifact
$legacyFirmwareMapHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $legacyFirmwareMapArtifact
$gpioFixFirmwareElfHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $gpioFixFirmwareElfArtifact
$gpioFixFirmwareMapHash =
    Get-FileHash -Algorithm SHA256 -LiteralPath $gpioFixFirmwareMapArtifact

$filesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $filesystemArtifact

$legacyFilesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $legacyFilesystemArtifact

$gpioFixFilesystemHash =
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $gpioFixFilesystemArtifact

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
    buildSystem = "PlatformIO"
    platformIoCore = $platformIoVersion
    platform = "platformio/espressif8266@4.2.1"
    framework = "arduino"
    board = "esp12e"
    flashLayout = "4M1M"
    profiles = [ordered]@{
        normal = [ordered]@{
            hardwareProfile = "normal"
            platformIoEnvironment = "normal"
            buildFlags = @()
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
            platformIoEnvironment = "legacy"
            buildFlags = @(
                "-DUSE_LEGACY_HARDWARE=1"
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
        gpioFix = [ordered]@{
            hardwareProfile = "gpio_fix"
            platformIoEnvironment = "gpio_fix"
            buildFlags = @(
                "-DUSE_GPIO_FIX_HARDWARE=1",
                "-DLED_WS2812_COLOR_ORDER=NEO_GRB"
            )
            firmware = [ordered]@{
                file = (Split-Path $gpioFixFirmwareArtifact -Leaf)
                size = (Get-Item $gpioFixFirmwareArtifact).Length
                sha256 = $gpioFixFirmwareHash.Hash
            }
            debug = [ordered]@{
                elf = [ordered]@{
                    file = (Split-Path $gpioFixFirmwareElfArtifact -Leaf)
                    size = (Get-Item $gpioFixFirmwareElfArtifact).Length
                    sha256 = $gpioFixFirmwareElfHash.Hash
                }
                map = [ordered]@{
                    file = (Split-Path $gpioFixFirmwareMapArtifact -Leaf)
                    size = (Get-Item $gpioFixFirmwareMapArtifact).Length
                    sha256 = $gpioFixFirmwareMapHash.Hash
                }
            }
            littleFs = [ordered]@{
                size = 1024000
                blockSize = 8192
                pageSize = 256
                file = (Split-Path $gpioFixFilesystemArtifact -Leaf)
                sha256 = $gpioFixFilesystemHash.Hash
            }
        }
    }
}

if ($IncludeTestHarness) {
    $manifest["profiles"]["test"] = [ordered]@{
        hardwareProfile = "normal"
        testHarnessApi = $true
        platformIoEnvironment = "test"
        buildFlags = @(
            "-DENABLE_TEST_HARNESS_API=1"
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
        platformIoEnvironment = "legacy_test"
        buildFlags = @(
            "-DUSE_LEGACY_HARDWARE=1",
            "-DENABLE_TEST_HARNESS_API=1"
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
Write-Host "Firmware GPIO_Fix: $gpioFixFirmwareArtifact"
Write-Host "Debug GPIO_Fix   : $gpioFixFirmwareElfArtifact / $gpioFixFirmwareMapArtifact"
Write-Host "LittleFS GPIO_Fix: $gpioFixFilesystemArtifact"
if ($IncludeTestHarness) {
    Write-Host "Firmware test   : $testFirmwareArtifact"
    Write-Host "Firmware legacy test: $legacyTestFirmwareArtifact"
}
Write-Host "Manifest        : $manifestPath"
