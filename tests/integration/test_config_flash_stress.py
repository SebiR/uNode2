from __future__ import annotations

import os
import time

import pytest

from helpers import step
from unode_client import UNodeClient


def _write_count() -> int:
    return max(0, int(os.environ.get("UNODE_CONFIG_FLASH_STRESS_WRITES", "0")))


def _write_interval_seconds() -> float:
    return max(
        0.05,
        float(os.environ.get("UNODE_CONFIG_FLASH_STRESS_INTERVAL", "1.0")),
    )


def test_persistent_config_flash_stress_isolated_from_network_soak(
    unode_client: UNodeClient,
) -> None:
    """Exercise repeated LittleFS config commits only when explicitly enabled."""

    writes = _write_count()
    if writes <= 0:
        pytest.skip(
            "Set UNODE_CONFIG_FLASH_STRESS_WRITES to run persistent flash stress"
        )

    interval = _write_interval_seconds()
    original = unode_client.get_config()
    initial_status = unode_client.get_json("/api/status")
    initial_boot_count = int(initial_status["bootCount"])
    minimum_heap = int(initial_status.get("minimumFreeHeap", 0))
    started = time.monotonic()

    step(
        "Starting isolated persistent config stress: "
        f"writes={writes} interval={interval:.2f}s "
        f"bootCount={initial_boot_count}"
    )

    try:
        for index in range(writes):
            candidate = original.copy()
            candidate["mergeMode"] = index % 2
            candidate["failsafeMode"] = (index // 2) % 4
            candidate["legacyArtPollReply"] = bool(index % 3 == 0)

            response = unode_client.save_config(candidate)
            assert response.get("appliedLive") is True

            status = unode_client.get_json("/api/status", timeout=2.0)
            minimum_heap = min(
                minimum_heap,
                int(status.get("minimumFreeHeap", minimum_heap)),
            )
            assert int(status["bootCount"]) == initial_boot_count, (
                "uNode rebooted during persistent config stress: "
                f"write={index + 1}/{writes}, "
                f"resetReason={status.get('resetReason')!r}, "
                f"resetInfo={status.get('resetInfo')!r}"
            )

            if index == 0 or (index + 1) % 10 == 0 or index + 1 == writes:
                step(
                    "Persistent config stress progress: "
                    f"{index + 1}/{writes}, "
                    f"freeHeap={status.get('freeHeap')}, "
                    f"maxFreeBlock={status.get('maxFreeBlock')}"
                )

            time.sleep(interval)
    finally:
        step("Restoring persisted configuration after flash stress")
        try:
            unode_client.save_config(original)
        except Exception as error:  # noqa: BLE001 - preserve the primary failure.
            step(f"Could not restore persisted configuration: {error}")

    final_status = unode_client.get_json("/api/status", timeout=2.0)
    elapsed = time.monotonic() - started
    step(
        "Persistent config stress summary: "
        f"writes={writes}, elapsed={elapsed:.1f}s, "
        f"minimumFreeHeap={minimum_heap}, "
        f"bootCount={final_status.get('bootCount')}"
    )

    assert int(final_status["bootCount"]) == initial_boot_count
