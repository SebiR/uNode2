from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_define(name: str) -> str:
    config_h = PROJECT_ROOT / "firmware" / "uNode_2" / "config.h"
    pattern = re.compile(rf"^\s*#define\s+{re.escape(name)}\s+(.+?)\s*$")

    for line in config_h.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()

    raise AssertionError(f"{name} not found in config.h")


def _firmware_version_from_defines() -> str:
    return ".".join(
        _read_define(part)
        for part in ("FW_VERSION_MAJOR", "FW_VERSION_MINOR", "FW_VERSION_PATCH")
    )


def test_littlefs_version_file_matches_firmware_defines() -> None:
    version_json = json.loads(
        (PROJECT_ROOT / "firmware" / "uNode_2" / "data" / "version.json").read_text(
            encoding="utf-8"
        )
    )

    assert version_json["version"] == _firmware_version_from_defines()
    assert int(version_json["configSchemaVersion"]) == int(
        _read_define("CONFIG_SCHEMA_VERSION")
    )


def test_uart_flash_helper_lists_normal_and_legacy_artifacts(tmp_path: Path) -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required to test flash_uart.ps1")

    artifact_names = [
        "uNode-0.99.0-firmware.bin",
        "uNode-0.99.0-littlefs.bin",
        "uNode-0.99.0_legacy-firmware.bin",
        "uNode-0.99.0_legacy-littlefs.bin",
    ]

    for name in artifact_names:
        (tmp_path / name).write_bytes(b"dummy")

    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "tools" / "flash_uart.ps1"),
            "-ArtifactsDir",
            str(tmp_path),
            "-ListOnly",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = result.stdout
    normal = "0.99.0 normal: uNode-0.99.0-firmware.bin / uNode-0.99.0-littlefs.bin"
    legacy = (
        "0.99.0 legacy: "
        "uNode-0.99.0_legacy-firmware.bin / uNode-0.99.0_legacy-littlefs.bin"
    )

    assert normal in output
    assert legacy in output
    assert output.index(normal) < output.index(legacy)


def test_ota_flash_helper_dry_run_targets_expected_update_endpoint(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required to test flash_ota.ps1")

    artifact_names = [
        "uNode-0.99.0-firmware.bin",
        "uNode-0.99.0-littlefs.bin",
        "uNode-0.99.0_legacy-firmware.bin",
        "uNode-0.99.0_legacy-littlefs.bin",
    ]

    for name in artifact_names:
        (tmp_path / name).write_bytes(b"dummy")

    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "tools" / "flash_ota.ps1"),
            "-ArtifactsDir",
            str(tmp_path),
            "-BaseUrl",
            "http://192.0.2.10",
            "-FirmwareOnly",
            "-DryRun",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        input="2\n",
        text=True,
        timeout=30,
    )

    assert "Profile   : legacy" in result.stdout
    assert (
        "Target    : http://192.0.2.10/api/update/firmware?size=5"
        in result.stdout
    )
    assert "Dry run: skipping OTA upload" in result.stdout
