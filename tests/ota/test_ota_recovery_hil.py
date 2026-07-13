"""Explicitly destructive OTA interruption and recovery tests.

This module is never part of the default regression suite. It requires the
RP2040 fixture to control both the active-low reset and recovery-button inputs,
plus an exact acknowledgement string. The LittleFS test deliberately destroys
the on-flash filesystem and then proves that the firmware-embedded recovery
page can reinstall a verified image.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import pytest

from helpers import request_artpoll_reply, step
from ota_helpers import (
    ReleaseArtifacts,
    interrupt_upload,
    resolve_release_artifacts,
    upload_file,
)
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


_ACKNOWLEDGEMENT = "I_UNDERSTAND_THIS_CAN_CORRUPT_FLASH"

pytestmark = pytest.mark.skipif(
    os.environ.get("UNODE_RUN_DESTRUCTIVE_OTA") != _ACKNOWLEDGEMENT,
    reason="Set UNODE_RUN_DESTRUCTIVE_OTA=" + _ACKNOWLEDGEMENT,
)


def _required_gpio(name: str) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AssertionError(f"{name} is required for destructive OTA recovery")
    return int(value, 0)


def _wait_for_json(
    client: UNodeClient,
    path: str,
    predicate: Callable[[dict], bool],
    *,
    timeout: float = 40.0,
) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    last_value: dict = {}
    while time.monotonic() < deadline:
        try:
            last_value = client.get_json(path, timeout=1.5)
            last_error = None
            if predicate(last_value):
                return last_value
        except Exception as error:  # noqa: BLE001 - reboot/reconnect is expected.
            last_error = error
        time.sleep(0.25)
    raise AssertionError(
        f"Timed out waiting for {path}; last={last_value}, error={last_error!r}"
    )


def _enter_recovery(
    tool: Rp2040DmxTool,
    client: UNodeClient,
    *,
    button_pin: int,
    reset_pin: int,
) -> dict:
    step(
        f"Entering physical recovery: hold GPIO{button_pin}, pulse reset GPIO{reset_pin}"
    )
    tool.gpio_release(button_pin)
    tool.gpio_release(reset_pin)
    tool.gpio_write(button_pin, 0)
    time.sleep(0.05)
    tool.gpio_pulse(reset_pin, value=0, duration_ms=250, release=True)
    # Keep the button asserted beyond the firmware's 250 ms boot debounce.
    time.sleep(0.75)
    tool.gpio_release(button_pin)

    return _wait_for_json(
        client,
        "/api/recovery/status",
        lambda value: str(value.get("chipId", "")) != "",
        timeout=45.0,
    )


def _pulse_reset(tool: Rp2040DmxTool, reset_pin: int) -> None:
    tool.gpio_pulse(reset_pin, value=0, duration_ms=250, release=True)


def _artifacts(normal_client: UNodeClient) -> ReleaseArtifacts:
    version = str(normal_client.get_json("/api/status")["firmware"])
    return resolve_release_artifacts(version)


def test_interrupted_firmware_upload_keeps_previous_firmware_bootable(
    unode_client: UNodeClient,
    unode_ip: str,
    rp2040_tool: Rp2040DmxTool,
    record_property,
) -> None:
    button_pin = _required_gpio("UNODE_BUTTON_GPIO_PIN")
    reset_pin = _required_gpio("UNODE_RESET_GPIO_PIN")
    artifacts = _artifacts(unode_client)
    before = unode_client.get_json("/api/status")
    recovery_client = UNodeClient(unode_client.base_url)

    try:
        recovery = _enter_recovery(
            rp2040_tool,
            recovery_client,
            button_pin=button_pin,
            reset_pin=reset_pin,
        )
        assert recovery["firmware"] == artifacts.version
        assert recovery["fsMounted"] is True

        payload = artifacts.firmware.read_bytes()
        interrupt_at = len(payload) // 3
        step(
            f"Interrupting firmware upload after {interrupt_at} of {len(payload)} bytes"
        )
        started = time.perf_counter()
        sent = interrupt_upload(
            recovery_client.base_url,
            "/api/update/firmware",
            payload,
            declared_size=len(payload),
            interrupt_after=interrupt_at,
            interrupt=lambda: _pulse_reset(rp2040_tool, reset_pin),
            filename=artifacts.firmware.name,
        )
        assert sent == interrupt_at, (
            f"Firmware upload transport stopped early at {sent} bytes"
        )

        restarted = _wait_for_json(
            unode_client,
            "/api/status",
            lambda value: value.get("recoveryMode") is False
            and int(value.get("bootCount", 0)) > int(before["bootCount"]),
        )
        recovery_ms = (time.perf_counter() - started) * 1000.0
        assert restarted["firmware"] == before["firmware"]
        assert restarted["webAssetVersionMatch"] is True
        request_artpoll_reply(unode_ip, timeout=5.0)
        step(
            "Interrupted firmware was not activated; previous release and "
            f"ArtPoll recovered after {recovery_ms:.0f} ms"
        )
        record_property(
            "metric.interruptedFirmwareOta",
            {
                "declaredBytes": len(payload),
                "bytesBeforeReset": sent,
                "percentBeforeReset": round(sent * 100.0 / len(payload), 1),
                "previousVersion": str(before["firmware"]),
                "versionAfterReset": str(restarted["firmware"]),
                "recoveryMs": round(recovery_ms, 1),
                "bootCountBefore": int(before["bootCount"]),
                "bootCountAfter": int(restarted["bootCount"]),
            },
        )
    finally:
        rp2040_tool.gpio_release(button_pin)
        rp2040_tool.gpio_release(reset_pin)


def test_corrupted_littlefs_is_recoverable_through_embedded_page(
    unode_client: UNodeClient,
    unode_ip: str,
    rp2040_tool: Rp2040DmxTool,
    record_property,
) -> None:
    button_pin = _required_gpio("UNODE_BUTTON_GPIO_PIN")
    reset_pin = _required_gpio("UNODE_RESET_GPIO_PIN")
    artifacts = _artifacts(unode_client)
    original_config = unode_client.get_config()
    auth = unode_client.get_json("/api/auth/status")
    assert auth.get("enabled") is False, (
        "Disable access control before the destructive LittleFS test; the "
        "recovery image intentionally replaces its password hash."
    )
    assert int(original_config.get("wifiMode", -1)) == 1, (
        "Run destructive LittleFS recovery while the node is in AP mode."
    )

    recovery_client = UNodeClient(unode_client.base_url)
    corruption_started = False
    restored = False
    recovery_status: dict = {}
    failure_mode = ""
    sent = 0
    started = 0.0

    def reinstall_filesystem() -> dict:
        nonlocal recovery_status
        recovery_status = _enter_recovery(
            rp2040_tool,
            recovery_client,
            button_pin=button_pin,
            reset_pin=reset_pin,
        )
        step(
            "Recovery API reports "
            f"fsMounted={recovery_status.get('fsMounted')}; uploading verified LittleFS"
        )
        response = upload_file(
            recovery_client.base_url,
            "/api/update/fs",
            artifacts.littlefs,
            timeout=120.0,
        )
        assert response.status == 200, response.body.decode(errors="replace")
        normal = _wait_for_json(
            unode_client,
            "/api/status",
            lambda value: value.get("recoveryMode") is False
            and value.get("webAssetVersionMatch") is True,
            timeout=45.0,
        )
        step("Verified LittleFS restored; restoring saved node configuration")
        fresh_client = UNodeClient(unode_client.base_url)
        saved = fresh_client.save_config(original_config)
        assert "restartRequired" in saved
        return normal

    try:
        initial_recovery = _enter_recovery(
            rp2040_tool,
            recovery_client,
            button_pin=button_pin,
            reset_pin=reset_pin,
        )
        assert initial_recovery["fsMounted"] is True

        image_size = artifacts.littlefs.stat().st_size
        poison = b"\xA5" * image_size
        interrupt_at = 128 * 1024
        step(
            "Overwriting the LittleFS superblocks with a deliberately invalid "
            f"stream and resetting after {interrupt_at} bytes"
        )
        corruption_started = True
        started = time.perf_counter()
        sent = interrupt_upload(
            recovery_client.base_url,
            "/api/update/fs",
            poison,
            declared_size=image_size,
            interrupt_after=interrupt_at,
            interrupt=lambda: _pulse_reset(rp2040_tool, reset_pin),
            filename="deliberately-invalid-littlefs.bin",
        )
        assert sent == interrupt_at, (
            f"LittleFS upload transport stopped early at {sent} bytes"
        )

        # Depending on which LittleFS metadata generation survived, the mount
        # may either fail completely or succeed with missing/corrupt files.
        # Both are valid power-loss outcomes and must lead to physical recovery.
        time.sleep(2.0)
        try:
            damaged_status = unode_client.get_json("/api/status", timeout=3.0)
        except Exception:  # noqa: BLE001 - a failed mount has no normal API.
            failure_mode = "mount-failed"
            step("Normal boot remained in the LittleFS mount-fault state")
        else:
            assert damaged_status.get("webAssetVersionMatch") is not True, (
                "Deliberately corrupted LittleFS unexpectedly retained valid web assets"
            )
            failure_mode = "mounted-with-corrupt-assets"
            step(
                "LittleFS mounted through redundant metadata, but web-asset "
                "validation correctly reports damaged/missing content"
            )

        normal = reinstall_filesystem()
        restored = True
        recovery_ms = (time.perf_counter() - started) * 1000.0
        assert normal["firmware"] == artifacts.version
        request_artpoll_reply(unode_ip, timeout=5.0)
        step(
            "Embedded recovery restored LittleFS and normal ArtPoll operation "
            f"after {recovery_ms:.0f} ms"
        )
        record_property(
            "metric.interruptedLittleFsOta",
            {
                "declaredBytes": image_size,
                "bytesBeforeReset": sent,
                "percentBeforeReset": round(sent * 100.0 / image_size, 1),
                "failureMode": failure_mode,
                "recoveryFsMounted": bool(recovery_status["fsMounted"]),
                "restoredVersion": str(normal["firmware"]),
                "totalRecoveryMs": round(recovery_ms, 1),
            },
        )
    finally:
        rp2040_tool.gpio_release(button_pin)
        rp2040_tool.gpio_release(reset_pin)
        if corruption_started and not restored:
            step("Test cleanup: attempting mandatory LittleFS recovery")
            reinstall_filesystem()
            rp2040_tool.gpio_release(button_pin)
            rp2040_tool.gpio_release(reset_pin)
