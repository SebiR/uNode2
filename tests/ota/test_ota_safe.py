"""Safe web-OTA validation and known-good update tests.

These tests reject malformed requests and then reinstall the currently running
release. They never intentionally interrupt a flash write. Run them separately
from the normal regression suite because successful updates reboot the node and
the LittleFS test replaces/restores its configuration.
"""

from __future__ import annotations

import os
import time

import pytest

from helpers import request_artpoll_reply, step, wait_for_node_restart
from ota_helpers import (
    ReleaseArtifacts,
    resolve_release_artifacts,
    upload_bytes,
    upload_file,
)
from unode_client import UNodeClient


pytestmark = pytest.mark.skipif(
    os.environ.get("UNODE_RUN_OTA") != "1",
    reason="Run through tools/test.sh --ota or tools/test.ps1 -Ota",
)


def _artifacts(client: UNodeClient) -> ReleaseArtifacts:
    status = client.get_json("/api/status")
    version = str(status["firmware"])
    artifacts = resolve_release_artifacts(version)
    step(
        f"Verified OTA release {artifacts.version} ({artifacts.profile}) "
        "against its SHA-256 manifest"
    )
    return artifacts


def _assert_failed_without_restart(
    client: UNodeClient,
    *,
    endpoint: str,
    payload: bytes,
    declared_size: int | str | None,
    expected_message: str,
) -> None:
    before = client.get_json("/api/status")
    response = upload_bytes(
        client.base_url,
        endpoint,
        payload,
        declared_size=declared_size,
        token=client.token,
    )
    text = response.body.decode("utf-8", errors="replace")
    assert response.status == 500, text
    assert expected_message.lower() in text.lower()

    # A successful OTA schedules a reboot after 700 ms. Waiting beyond that
    # distinguishes a clean rejection from an accidentally accepted image.
    time.sleep(1.0)
    after = client.get_json("/api/status")
    assert int(after["bootCount"]) == int(before["bootCount"])
    assert after["firmware"] == before["firmware"]


def test_ota_rejects_missing_invalid_and_oversized_declarations(
    unode_client: UNodeClient,
) -> None:
    step("Checking OTA request-size validation without changing active images")

    cases = (
        (
            "/api/update/firmware",
            None,
            "Upload size is missing or invalid",
        ),
        (
            "/api/update/firmware",
            "not-a-number",
            "Upload size is missing or invalid",
        ),
        (
            "/api/update/firmware",
            16 * 1024 * 1024,
            "Firmware image is too large",
        ),
        (
            "/api/update/fs",
            64,
            "LittleFS image size does not match",
        ),
    )
    for endpoint, declared_size, message in cases:
        step(f"Expecting rejection from {endpoint} with size={declared_size!r}")
        _assert_failed_without_restart(
            unode_client,
            endpoint=endpoint,
            payload=b"\x00" * 64,
            declared_size=declared_size,
            expected_message=message,
        )


def test_ota_rejects_invalid_firmware_magic_and_truncated_upload(
    unode_client: UNodeClient,
) -> None:
    step("Checking invalid firmware header rejection")
    _assert_failed_without_restart(
        unode_client,
        endpoint="/api/update/firmware",
        payload=b"\x00" * 128,
        declared_size=128,
        expected_message="Magic byte is not 0xE9",
    )

    step("Checking declared-versus-written firmware length validation")
    _assert_failed_without_restart(
        unode_client,
        endpoint="/api/update/firmware",
        payload=b"\xE9" + b"\x00" * 126,
        declared_size=256,
        expected_message="Upload size mismatch",
    )


def test_known_good_firmware_update_reboots_into_same_release(
    unode_client: UNodeClient,
    unode_ip: str,
    record_property,
) -> None:
    artifacts = _artifacts(unode_client)
    before = unode_client.get_json("/api/status")

    step(
        f"Uploading known-good firmware {artifacts.firmware.name} "
        f"({artifacts.firmware.stat().st_size} bytes)"
    )
    started = time.perf_counter()
    response = upload_file(
        unode_client.base_url,
        "/api/update/firmware",
        artifacts.firmware,
        token=unode_client.token,
    )
    assert response.status == 200, response.body.decode(errors="replace")

    restarted = wait_for_node_restart(
        unode_client,
        previous_boot_count=int(before["bootCount"]),
        timeout=35.0,
    )
    recovery_ms = (time.perf_counter() - started) * 1000.0
    assert restarted["firmware"] == artifacts.version
    assert restarted["webAssetVersionMatch"] is True
    request_artpoll_reply(unode_ip, timeout=5.0)
    step(f"Firmware OTA recovered HTTP and ArtPoll after {recovery_ms:.0f} ms")

    unode_client.token = ""
    unode_client.ensure_authenticated()
    record_property(
        "metric.otaFirmware",
        {
            "version": artifacts.version,
            "profile": artifacts.profile,
            "bytes": artifacts.firmware.stat().st_size,
            "sha256": artifacts.firmware_sha256,
            "recoveryMs": round(recovery_ms, 1),
            "bootCountBefore": int(before["bootCount"]),
            "bootCountAfter": int(restarted["bootCount"]),
        },
    )


def test_known_good_littlefs_update_restores_web_assets_and_config(
    unode_client: UNodeClient,
    unode_ip: str,
    record_property,
) -> None:
    artifacts = _artifacts(unode_client)
    before = unode_client.get_json("/api/status")
    original_config = unode_client.get_config()
    auth = unode_client.get_json("/api/auth/status")
    assert auth.get("enabled") is False, (
        "The LittleFS image replaces the password hash. Disable access control "
        "before running the safe LittleFS OTA test."
    )
    assert int(original_config.get("wifiMode", -1)) == 1, (
        "Run the LittleFS OTA test while the node is in AP mode; the release "
        "image contains default AP configuration."
    )

    step(
        f"Uploading known-good LittleFS {artifacts.littlefs.name} "
        f"({artifacts.littlefs.stat().st_size} bytes)"
    )
    started = time.perf_counter()
    response = upload_file(
        unode_client.base_url,
        "/api/update/fs",
        artifacts.littlefs,
        token=unode_client.token,
        timeout=120.0,
    )
    assert response.status == 200, response.body.decode(errors="replace")

    restarted = wait_for_node_restart(
        unode_client,
        previous_boot_count=int(before["bootCount"]),
        timeout=40.0,
    )
    recovery_ms = (time.perf_counter() - started) * 1000.0
    assert restarted["firmware"] == artifacts.version
    assert restarted["webAssetVersion"] == artifacts.version
    assert restarted["webAssetVersionMatch"] is True

    step("Restoring the configuration saved before the LittleFS replacement")
    unode_client.token = ""
    unode_client.ensure_authenticated()
    saved = unode_client.save_config(original_config)
    assert "restartRequired" in saved
    restored = unode_client.get_config()
    for key, expected in original_config.items():
        assert restored.get(key) == expected, key

    request_artpoll_reply(unode_ip, timeout=5.0)
    step(f"LittleFS OTA recovered web assets and ArtPoll after {recovery_ms:.0f} ms")
    record_property(
        "metric.otaLittleFs",
        {
            "version": artifacts.version,
            "bytes": artifacts.littlefs.stat().st_size,
            "sha256": artifacts.littlefs_sha256,
            "recoveryMs": round(recovery_ms, 1),
            "configRestored": True,
            "bootCountBefore": int(before["bootCount"]),
            "bootCountAfter": int(restarted["bootCount"]),
        },
    )
