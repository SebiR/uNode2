param(
    [string]$ArtifactsDir = "",
    [string]$Port = "",
    [int]$Baud = 512000,
    [switch]$FirmwareOnly,
    [switch]$LittleFsOnly,
    [switch]$ListOnly,
    [switch]$DryRun,
    [switch]$NoRemember
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot "..")

if ([string]::IsNullOrWhiteSpace($ArtifactsDir)) {
    $ArtifactsDir =
        Join-Path $projectRoot "artifacts\release"
}

$ArtifactsDir =
    Resolve-Path $ArtifactsDir

$settingsDir =
    Join-Path $projectRoot "artifacts"

$settingsPath =
    Join-Path $settingsDir "flash_uart.settings.json"

$littleFsAddress = "0x300000"

function ConvertTo-SemVerKey {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $parts =
        $Version.Split(".") |
        ForEach-Object { [int]$_ }

    while ($parts.Count -lt 3) {
        $parts += 0
    }

    return (($parts[0] * 1000000) + ($parts[1] * 1000) + $parts[2])
}

function Get-ReleaseCandidates {
    $firmwareFiles =
        Get-ChildItem `
            -LiteralPath $ArtifactsDir `
            -Filter "uNode-*-firmware.bin" `
            -File

    $candidates = @()

    foreach ($firmware in $firmwareFiles) {
        $match =
            [regex]::Match(
                $firmware.Name,
                "^uNode-(?<version>\d+\.\d+\.\d+)(?<suffix>_(?:legacy|gpio_fix))?-firmware\.bin$")

        if (!$match.Success) {
            continue
        }

        $version =
            $match.Groups["version"].Value

        $suffix =
            $match.Groups["suffix"].Value

        $profile =
            switch ($suffix) {
                "_legacy" { "legacy" }
                "_gpio_fix" { "gpio_fix" }
                default { "normal" }
            }

        $profileOrder =
            switch ($profile) {
                "normal" { 0 }
                "gpio_fix" { 1 }
                default { 2 }
            }

        $littleFs =
            Join-Path $ArtifactsDir "uNode-$version$suffix-littlefs.bin"

        $manifest =
            Join-Path $ArtifactsDir "uNode-$version-manifest.json"

        $candidates += [pscustomobject]@{
            Version = $version
            VersionKey = ConvertTo-SemVerKey $version
            Profile = $profile
            ProfileOrder = $profileOrder
            Suffix = $suffix
            Firmware = $firmware.FullName
            LittleFs = $littleFs
            LittleFsExists = Test-Path $littleFs
            Manifest = $manifest
            ManifestExists = Test-Path $manifest
        }
    }

    return $candidates |
        Sort-Object `
            -Property @{ Expression = "VersionKey"; Descending = $true },
                      @{ Expression = "ProfileOrder"; Descending = $false }
}

function Select-ReleaseCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Candidates
    )

    if ($Candidates.Count -eq 0) {
        throw "No release firmware artifacts found in $ArtifactsDir. Run .\firmware\uNode_2\tools\build_release.ps1 first."
    }

    Write-Host ""
    Write-Host "Available uNode release artifacts" -ForegroundColor Cyan

    for ($index = 0; $index -lt $Candidates.Count; $index++) {
        $candidate = $Candidates[$index]
        $fsText =
            if ($candidate.LittleFsExists) {
                Split-Path $candidate.LittleFs -Leaf
            } else {
                "missing LittleFS"
            }

        Write-Host ("[{0}] {1,-8} {2,-6} FW: {3}  FS: {4}" -f ($index + 1), $candidate.Version, $candidate.Profile, (Split-Path $candidate.Firmware -Leaf), $fsText)
    }

    while ($true) {
        $choice =
            Read-Host "Select firmware version/profile by number"

        $number = 0
        if ([int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $Candidates.Count) {
            $selected =
                $Candidates[$number - 1]

            if (!$FirmwareOnly -and !$selected.LittleFsExists) {
                throw "LittleFS image missing for selected artifact: $($selected.LittleFs)"
            }

            return $selected
        }

        Write-Host "Please enter a number between 1 and $($Candidates.Count)." -ForegroundColor Yellow
    }
}

function Get-SerialPorts {
    $script = @'
import json
from serial.tools import list_ports

ports = []
for port in list_ports.comports():
    ports.append({
        "device": port.device,
        "description": port.description,
        "hwid": port.hwid,
        "vid": port.vid,
        "pid": port.pid,
        "serialNumber": port.serial_number,
        "manufacturer": port.manufacturer,
        "product": port.product,
    })

print(json.dumps(ports))
'@

    $tempScript =
        Join-Path $env:TEMP ("unode-list-ports-{0}.py" -f ([guid]::NewGuid().ToString("N")))

    try {
        Set-Content `
            -LiteralPath $tempScript `
            -Value $script `
            -Encoding UTF8

        $json =
            python $tempScript

        if ($LASTEXITCODE -ne 0) {
            throw "Could not enumerate serial ports with Python/pyserial"
        }
    } finally {
        if (Test-Path $tempScript) {
            Remove-Item `
                -LiteralPath $tempScript `
                -Force
        }
    }

    $parsed =
        ($json -join "`n") |
        ConvertFrom-Json

    foreach ($entry in $parsed) {
        Write-Output $entry
    }
}

function Format-VidPid {
    param(
        [object]$PortInfo
    )

    if ($null -eq $PortInfo.vid -or $null -eq $PortInfo.pid) {
        return "VID:PID n/a"
    }

    $vid =
        [int]$PortInfo.vid

    $productId =
        [int]$PortInfo.pid

    return "VID:PID $($vid.ToString("X4")):$($productId.ToString("X4"))"
}

function Read-FlashSettings {
    if (!(Test-Path $settingsPath)) {
        return $null
    }

    try {
        return Get-Content `
            -LiteralPath $settingsPath `
            -Raw |
            ConvertFrom-Json
    } catch {
        return $null
    }
}

function Save-FlashSettings {
    param(
        [Parameter(Mandatory = $true)]
        [object]$PortInfo
    )

    if ($NoRemember) {
        return
    }

    New-Item `
        -ItemType Directory `
        -Path $settingsDir `
        -Force |
        Out-Null

    [ordered]@{
        device = $PortInfo.device
        vid = $PortInfo.vid
        pid = $PortInfo.pid
        serialNumber = $PortInfo.serialNumber
        description = $PortInfo.description
        baud = $Baud
    } |
        ConvertTo-Json -Depth 3 |
        Set-Content `
            -LiteralPath $settingsPath `
            -Encoding UTF8
}

function Select-SerialPort {
    param(
        [object[]]$Ports
    )

    if ($Ports.Count -eq 0) {
        throw "No serial ports found"
    }

    if (![string]::IsNullOrWhiteSpace($Port)) {
        $selected =
            $Ports |
            Where-Object { $_.device -ieq $Port } |
            Select-Object -First 1

        if (!$selected) {
            throw "Requested serial port '$Port' was not found"
        }

        return $selected
    }

    $settings =
        Read-FlashSettings

    if ($settings) {
        $matches =
            $Ports |
            Where-Object {
                $vidMatch = (($null -ne $settings.vid) -and ($null -ne $_.vid) -and ([int]$_.vid -eq [int]$settings.vid))
                $pidMatch = (($null -ne $settings.pid) -and ($null -ne $_.pid) -and ([int]$_.pid -eq [int]$settings.pid))
                $serialMatch = ([string]::IsNullOrWhiteSpace($settings.serialNumber) -or ($_.serialNumber -eq $settings.serialNumber))

                $vidMatch -and $pidMatch -and $serialMatch
            }

        if (@($matches).Count -eq 1) {
            $match =
                @($matches)[0]

            Write-Host (
                "Using remembered serial adapter: {0} ({1}, {2})" -f $match.device, (Format-VidPid $match), $match.description) `
                -ForegroundColor Cyan

            return $match
        }
    }

    Write-Host ""
    Write-Host "Available serial ports" -ForegroundColor Cyan

    for ($index = 0; $index -lt $Ports.Count; $index++) {
        $portInfo =
            $Ports[$index]

        Write-Host ("[{0}] {1,-6} {2,-18} {3}" -f ($index + 1), $portInfo.device, (Format-VidPid $portInfo), $portInfo.description)

        if (![string]::IsNullOrWhiteSpace($portInfo.serialNumber)) {
            Write-Host ("    Serial: {0}" -f $portInfo.serialNumber)
        }
    }

    while ($true) {
        $choice =
            Read-Host "Select serial port by number"

        $number = 0
        if ([int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $Ports.Count) {
            return $Ports[$number - 1]
        }

        Write-Host "Please enter a number between 1 and $($Ports.Count)." -ForegroundColor Yellow
    }
}

function Get-Esp8266PlatformPath {
    $paths =
        Get-ChildItem `
            -Path (Join-Path $env:LOCALAPPDATA "Arduino15\packages\esp8266\hardware\esp8266") `
            -Directory |
        Sort-Object Name -Descending

    if (!$paths) {
        throw "ESP8266 Arduino core not found below Arduino15\packages"
    }

    return $paths[0].FullName
}

function Invoke-EspUpload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Address,

        [Parameter(Mandatory = $true)]
        [string]$ImagePath,

        [Parameter(Mandatory = $true)]
        [string]$SelectedPort
    )

    $platformPath =
        Get-Esp8266PlatformPath

    $uploadScript =
        Join-Path $platformPath "tools\upload.py"

    if (!(Test-Path $uploadScript)) {
        throw "ESP8266 upload.py not found at $uploadScript"
    }

    Write-Host ""
    Write-Host (
        "Flashing {0} to {1} at {2} baud on {3}" -f (Split-Path $ImagePath -Leaf), $Address, $Baud, $SelectedPort) `
        -ForegroundColor Cyan

    if ($DryRun) {
        Write-Host "Dry run: skipping upload.py invocation" -ForegroundColor Yellow
        return
    }

    & python `
        -I `
        $uploadScript `
        --chip esp8266 `
        --port $SelectedPort `
        --baud $Baud `
        --before default_reset `
        --after hard_reset `
        write_flash `
        $Address `
        $ImagePath

    if ($LASTEXITCODE -ne 0) {
        throw "Flashing failed for $ImagePath"
    }
}

if ($FirmwareOnly -and $LittleFsOnly) {
    throw "-FirmwareOnly and -LittleFsOnly cannot be used together"
}

Write-Host "uNode UART flash helper" -ForegroundColor Cyan
Write-Host "Artifacts : $ArtifactsDir"
Write-Host "Baud      : $Baud"
if ($DryRun) {
    Write-Host "Mode      : dry run, no flash writes" -ForegroundColor Yellow
}

$candidates =
    @(Get-ReleaseCandidates)

$ports =
    @(Get-SerialPorts)

if ($ListOnly) {
    Write-Host ""
    Write-Host "Artifacts" -ForegroundColor Cyan
    $candidates |
        ForEach-Object {
            Write-Host ("- {0} {1}: {2} / {3}" -f $_.Version, $_.Profile, (Split-Path $_.Firmware -Leaf), (Split-Path $_.LittleFs -Leaf))
        }

    Write-Host ""
    Write-Host "Serial ports" -ForegroundColor Cyan
    $ports |
        ForEach-Object {
            $vidPid =
                Format-VidPid $_

            Write-Host "- $($_.device): $vidPid, $($_.description)"
        }

    return
}

$selectedArtifact =
    Select-ReleaseCandidate $candidates

$selectedPort =
    Select-SerialPort $ports

Save-FlashSettings $selectedPort

Write-Host ""
Write-Host "Selected artifact" -ForegroundColor Cyan
Write-Host "Version   : $($selectedArtifact.Version)"
Write-Host "Profile   : $($selectedArtifact.Profile)"
Write-Host "Firmware  : $($selectedArtifact.Firmware)"
Write-Host "LittleFS  : $($selectedArtifact.LittleFs)"
Write-Host "Port      : $($selectedPort.device) ($(Format-VidPid $selectedPort))"

if (!$LittleFsOnly) {
    Invoke-EspUpload `
        -Address "0x0" `
        -ImagePath $selectedArtifact.Firmware `
        -SelectedPort $selectedPort.device
}

if (!$FirmwareOnly) {
    Invoke-EspUpload `
        -Address $littleFsAddress `
        -ImagePath $selectedArtifact.LittleFs `
        -SelectedPort $selectedPort.device
}

Write-Host ""
Write-Host "UART flash complete" -ForegroundColor Green
