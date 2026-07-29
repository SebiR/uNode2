param(
    [string]$ArtifactsDir = "",
    [string]$NodeIp = "2.0.0.1",
    [string]$BaseUrl = "",
    [string]$Password = "",
    [switch]$FirmwareOnly,
    [switch]$LittleFsOnly,
    [switch]$ListOnly,
    [switch]$DryRun
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

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $BaseUrl = "http://$NodeIp"
}

$BaseUrl =
    $BaseUrl.TrimEnd("/")

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
            FirmwareSize = $firmware.Length
            LittleFs = $littleFs
            LittleFsExists = Test-Path $littleFs
            LittleFsSize = if (Test-Path $littleFs) { (Get-Item $littleFs).Length } else { 0 }
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

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Path,

        [string]$Body = "",

        [hashtable]$Headers = @{}
    )

    $uri =
        "$BaseUrl$Path"

    $parameters = @{
        Uri = $uri
        Method = $Method
        Headers = $Headers
        TimeoutSec = 10
    }

    if ($Body.Length -gt 0) {
        $parameters["Body"] = $Body
        $parameters["ContentType"] = "application/json"
    }

    $response =
        Invoke-WebRequest @parameters

    if (!$response.Content) {
        return @{}
    }

    return $response.Content |
        ConvertFrom-Json
}

function Get-OtaAuthHeaders {
    $status =
        Invoke-JsonRequest `
            -Method "GET" `
            -Path "/api/auth/status"

    if (!$status.enabled) {
        return @{}
    }

    if ([string]::IsNullOrWhiteSpace($Password)) {
        throw "The node has API authentication enabled. Re-run with -Password."
    }

    $loginBody =
        (@{ password = $Password } | ConvertTo-Json -Compress)

    $login =
        Invoke-JsonRequest `
            -Method "POST" `
            -Path "/api/auth/login" `
            -Body $loginBody

    if ([string]::IsNullOrWhiteSpace($login.token)) {
        throw "Login succeeded but no auth token was returned"
    }

    return @{
        "X-uNode-Auth" = [string]$login.token
    }
}

function Invoke-OtaUpload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ImagePath,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [hashtable]$Headers
    )

    $file =
        Get-Item -LiteralPath $ImagePath

    $uri =
        "${BaseUrl}${Path}?size=$($file.Length)"

    Write-Host ""
    Write-Host ("Uploading {0}: {1} ({2} bytes)" -f $Label, $file.Name, $file.Length) -ForegroundColor Cyan
    Write-Host "Target    : $uri"

    if ($DryRun) {
        Write-Host "Dry run: skipping OTA upload" -ForegroundColor Yellow
        return
    }

    Add-Type -AssemblyName System.Net.Http

    $client =
        New-Object System.Net.Http.HttpClient

    foreach ($key in $Headers.Keys) {
        $client.DefaultRequestHeaders.Remove($key) | Out-Null
        $client.DefaultRequestHeaders.Add($key, [string]$Headers[$key])
    }

    $stream = $null
    $multipart = $null

    try {
        $multipart =
            New-Object System.Net.Http.MultipartFormDataContent

        $stream =
            [System.IO.File]::OpenRead($file.FullName)

        $fileContent =
            New-Object System.Net.Http.StreamContent($stream)

        $fileContent.Headers.ContentType =
            [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/octet-stream")

        $multipart.Add(
            $fileContent,
            "file",
            $file.Name)

        $response =
            $client.PostAsync($uri, $multipart).GetAwaiter().GetResult()

        $responseText =
            $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

        if (!$response.IsSuccessStatusCode) {
            throw "OTA upload failed with HTTP $([int]$response.StatusCode): $responseText"
        }

        Write-Host $responseText -ForegroundColor Green
    } finally {
        if ($multipart) {
            $multipart.Dispose()
        } elseif ($stream) {
            $stream.Dispose()
        }

        $client.Dispose()
    }
}

if ($FirmwareOnly -and $LittleFsOnly) {
    throw "-FirmwareOnly and -LittleFsOnly cannot be used together"
}

Write-Host "uNode OTA flash helper" -ForegroundColor Cyan
Write-Host "Artifacts : $ArtifactsDir"
Write-Host "Base URL  : $BaseUrl"
if ($DryRun) {
    Write-Host "Mode      : dry run, no OTA writes" -ForegroundColor Yellow
}

$candidates =
    @(Get-ReleaseCandidates)

if ($ListOnly) {
    Write-Host ""
    Write-Host "Artifacts" -ForegroundColor Cyan
    $candidates |
        ForEach-Object {
            Write-Host ("- {0} {1}: {2} / {3}" -f $_.Version, $_.Profile, (Split-Path $_.Firmware -Leaf), (Split-Path $_.LittleFs -Leaf))
        }

    return
}

if (!$FirmwareOnly -and !$LittleFsOnly) {
    throw "OTA updates restart the node after each upload. Use -FirmwareOnly or -LittleFsOnly for an explicit one-step OTA update."
}

$selectedArtifact =
    Select-ReleaseCandidate $candidates

Write-Host ""
Write-Host "Selected artifact" -ForegroundColor Cyan
Write-Host "Version   : $($selectedArtifact.Version)"
Write-Host "Profile   : $($selectedArtifact.Profile)"
Write-Host "Firmware  : $($selectedArtifact.Firmware)"
Write-Host "LittleFS  : $($selectedArtifact.LittleFs)"

$headers =
    if ($DryRun) {
        @{}
    } else {
        Get-OtaAuthHeaders
    }

if ($FirmwareOnly) {
    Invoke-OtaUpload `
        -Path "/api/update/firmware" `
        -ImagePath $selectedArtifact.Firmware `
        -Label "Firmware" `
        -Headers $headers
}

if ($LittleFsOnly) {
    Invoke-OtaUpload `
        -Path "/api/update/fs" `
        -ImagePath $selectedArtifact.LittleFs `
        -Label "LittleFS" `
        -Headers $headers
}

Write-Host ""
Write-Host "OTA upload request complete. The node should restart." -ForegroundColor Green
