param(
    [switch]$Integration,
    [switch]$Ota,
    [switch]$DestructiveOta,
    [switch]$Reconnection,
    [string]$NodeIp = "",
    [string]$BaseUrl = "",
    [string]$Password = "",
    [string]$Rp2040Port = "",
    [int]$ButtonGpio = -1,
    [int]$ResetGpio = -1,
    [ValidateSet("normal", "legacy", "gpio_fix")]
    [string]$OtaProfile = "normal",
    [string]$OtaArtifactsDir = "",
    [int]$SoakSeconds = 0,
    [int]$DmxSoakSeconds = 0,
    [int]$LatencySamples = 0,
    [double]$LatencyTimeout = 0,
    [int]$DropoutSamples = 0,
    [double]$DropoutTimeout = 0,
    [double]$DropoutInterval = -1,
    [int]$DropoutAllowedLosses = -1,
    [double]$ArtNetSubscriberRefresh = 0,
    [double]$SoakInterval = 0,
    [double]$SoakGrace = 0,
    [string]$ReportJson = "",
    [string]$Path = ""
)

$ErrorActionPreference = "Stop"

$projectRoot =
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )

Set-Location $projectRoot

if ($Ota -or $DestructiveOta -or $Reconnection)
{
    $Integration = $true
}

if ($BaseUrl.Length -eq 0)
{
    if ($Integration -and $NodeIp.Length -eq 0)
    {
        Write-Host "Discover : ArtPoll on available IPv4 interfaces" -ForegroundColor Cyan
        $discoveredNodeIp =
            python .\tools\discover_unode.py --first-ip --timeout 1.5

        if ($LASTEXITCODE -eq 0 -and $discoveredNodeIp.Length -gt 0)
        {
            $NodeIp =
                $discoveredNodeIp.Trim()
            Write-Host "Found    : $NodeIp" -ForegroundColor Green
        }
        else
        {
            $NodeIp = "2.0.0.1"
            Write-Host "Found    : none, falling back to $NodeIp" -ForegroundColor Yellow
        }
    }
    elseif ($NodeIp.Length -eq 0)
    {
        $NodeIp = "2.0.0.1"
    }

    $BaseUrl = "http://$NodeIp"
}
elseif ($NodeIp.Length -eq 0)
{
    $NodeIp =
        ([Uri]$BaseUrl).Host
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

    if ($Reconnection)
    {
        $env:UNODE_RUN_RECONNECTION = "1"
    }
    else
    {
        Remove-Item Env:\UNODE_RUN_RECONNECTION -ErrorAction SilentlyContinue
    }

    if ($Password.Length -gt 0)
    {
        $env:UNODE_PASSWORD = $Password
    }

    if ($ReportJson.Length -gt 0)
    {
        $env:UNODE_TEST_REPORT_JSON = $ReportJson
    }
    else
    {
        Remove-Item Env:\UNODE_TEST_REPORT_JSON -ErrorAction SilentlyContinue
    }

    if ($Rp2040Port.Length -gt 0)
    {
        $env:UNODE_RP2040_PORT = $Rp2040Port
    }
    else
    {
        Remove-Item Env:\UNODE_RP2040_PORT -ErrorAction SilentlyContinue
    }

    if ($ButtonGpio -ge 0)
    {
        $env:UNODE_BUTTON_GPIO_PIN = "$ButtonGpio"
    }

    if ($ResetGpio -ge 0)
    {
        $env:UNODE_RESET_GPIO_PIN = "$ResetGpio"
    }

    if ($Ota -or $DestructiveOta)
    {
        $env:UNODE_OTA_PROFILE = $OtaProfile
        if ($OtaArtifactsDir.Length -gt 0)
        {
            $env:UNODE_OTA_ARTIFACTS_DIR =
                (Resolve-Path $OtaArtifactsDir).Path
        }
        else
        {
            $env:UNODE_OTA_ARTIFACTS_DIR =
                Join-Path $projectRoot "artifacts\release"
        }
    }

    if ($DestructiveOta)
    {
        $env:UNODE_RUN_DESTRUCTIVE_OTA =
            "I_UNDERSTAND_THIS_CAN_CORRUPT_FLASH"
        Remove-Item Env:\UNODE_RUN_OTA -ErrorAction SilentlyContinue
    }
    elseif ($Ota)
    {
        $env:UNODE_RUN_OTA = "1"
        Remove-Item Env:\UNODE_RUN_DESTRUCTIVE_OTA -ErrorAction SilentlyContinue
    }
    else
    {
        Remove-Item Env:\UNODE_RUN_OTA -ErrorAction SilentlyContinue
        Remove-Item Env:\UNODE_RUN_DESTRUCTIVE_OTA -ErrorAction SilentlyContinue
        Remove-Item Env:\UNODE_OTA_PROFILE -ErrorAction SilentlyContinue
        Remove-Item Env:\UNODE_OTA_ARTIFACTS_DIR -ErrorAction SilentlyContinue
    }

    if ($SoakSeconds -gt 0)
    {
        $env:UNODE_SOAK_SECONDS = "$SoakSeconds"
    }

    if ($DmxSoakSeconds -gt 0)
    {
        $env:UNODE_DMX_SOAK_SECONDS = "$DmxSoakSeconds"
    }

    if ($LatencySamples -gt 0)
    {
        $env:UNODE_LATENCY_SAMPLES = "$LatencySamples"
    }

    if ($LatencyTimeout -gt 0)
    {
        $env:UNODE_LATENCY_TIMEOUT = "$LatencyTimeout"
    }

    if ($DropoutSamples -gt 0)
    {
        $env:UNODE_DROPOUT_SAMPLES = "$DropoutSamples"
    }

    if ($DropoutTimeout -gt 0)
    {
        $env:UNODE_DROPOUT_TIMEOUT = "$DropoutTimeout"
    }

    if ($DropoutInterval -ge 0)
    {
        $env:UNODE_DROPOUT_INTERVAL = "$DropoutInterval"
    }

    if ($DropoutAllowedLosses -ge 0)
    {
        $env:UNODE_DROPOUT_ALLOWED_LOSSES = "$DropoutAllowedLosses"
    }

    if ($ArtNetSubscriberRefresh -gt 0)
    {
        $env:UNODE_ARTNET_SUBSCRIBER_REFRESH = "$ArtNetSubscriberRefresh"
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
        if ($DestructiveOta)
        {
            $Path = "tests/ota/test_ota_recovery_hil.py"
        }
        elseif ($Ota)
        {
            $Path = "tests/ota/test_ota_safe.py"
        }
        elseif ($Reconnection)
        {
            $Path = "tests/integration/test_network_reconnection.py"
        }
        else
        {
            $Path = "tests/integration"
        }
    }

    $pytestArgs = @("-s", "-vv", $Path)

    Write-Host "Preflight: checking uNode at $BaseUrl" -ForegroundColor Cyan
    python .\tools\check_unode.py --base-url $BaseUrl
    if ($LASTEXITCODE -ne 0)
    {
        exit $LASTEXITCODE
    }

    Write-Host "Mode    : integration" -ForegroundColor Yellow
    Write-Host "Node IP : $env:UNODE_IP"
    Write-Host "Base URL: $env:UNODE_BASE_URL"
    if ($env:UNODE_RP2040_PORT)
    {
        Write-Host "RP2040  : $env:UNODE_RP2040_PORT"
    }
    if ($Ota)
    {
        Write-Host "OTA     : safe ($env:UNODE_OTA_PROFILE)" -ForegroundColor Cyan
    }
    if ($DestructiveOta)
    {
        Write-Host "OTA     : DESTRUCTIVE recovery ($env:UNODE_OTA_PROFILE)" -ForegroundColor Red
    }
    if ($Reconnection)
    {
        Write-Host "Reconnect: controlled Client Wi-Fi outage" -ForegroundColor Cyan
    }
    if ($env:UNODE_SOAK_SECONDS)
    {
        Write-Host "Soak    : $env:UNODE_SOAK_SECONDS seconds"
    }
    if ($env:UNODE_DMX_SOAK_SECONDS)
    {
        Write-Host "DMX Soak: $env:UNODE_DMX_SOAK_SECONDS seconds"
    }
    if ($env:UNODE_LATENCY_SAMPLES)
    {
        Write-Host "Latency : $env:UNODE_LATENCY_SAMPLES samples"
    }
    if ($env:UNODE_DROPOUT_SAMPLES)
    {
        Write-Host "Dropout : $env:UNODE_DROPOUT_SAMPLES samples"
    }
    if ($env:UNODE_TEST_REPORT_JSON)
    {
        Write-Host "Report  : $env:UNODE_TEST_REPORT_JSON"
    }
}
else
{
    Remove-Item Env:\UNODE_RUN_INTEGRATION -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_RUN_RECONNECTION -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DMX_SOAK_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_LATENCY_SAMPLES -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_LATENCY_TIMEOUT -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DROPOUT_SAMPLES -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DROPOUT_TIMEOUT -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DROPOUT_INTERVAL -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_DROPOUT_ALLOWED_LOSSES -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_ARTNET_SUBSCRIBER_REFRESH -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_INTERVAL -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_SOAK_REACHABILITY_GRACE -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_TEST_REPORT_JSON -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_RUN_OTA -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_RUN_DESTRUCTIVE_OTA -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_OTA_PROFILE -ErrorAction SilentlyContinue
    Remove-Item Env:\UNODE_OTA_ARTIFACTS_DIR -ErrorAction SilentlyContinue

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
