from __future__ import annotations

import time

from helpers import step, wait_for_node_restart, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


def test_bus_guard_mode_is_persisted_and_requires_restart(
    unode_client: UNodeClient,
    preserved_config: dict,
) -> None:
    original_mode = int(preserved_config.get("busGuardMode", 0))
    requested_mode = 0 if original_mode == 1 else 1

    config = preserved_config.copy()
    config["busGuardMode"] = requested_mode

    step(f"Saving Bus Guarding mode {requested_mode}")
    response = unode_client.save_config(config)

    assert response.get("restartRequired") is True
    assert response.get("appliedLive") is False

    step("Reading config back and verifying Bus Guarding mode was persisted")
    saved_config = unode_client.get_config()
    assert int(saved_config["busGuardMode"]) == requested_mode

    step("Checking that /api/status exposes the configured Bus Guarding mode")
    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("busGuardMode", -1)) == requested_mode,
    )
    assert int(status["busGuardMode"]) == requested_mode


def test_bus_guard_detects_physical_dmx_at_boot_and_switches_to_input(
    unode_client: UNodeClient,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX before boot guard runs.
    config["busGuardMode"] = 1  # Auto input on boot.

    step("Configuring uNode for boot-time Bus Guarding from DMX output mode")
    response = unode_client.save_config(config)
    assert response.get("restartRequired") is True

    before = unode_client.get_json("/api/status")
    initial_boot_count = int(before["bootCount"])

    try:
        step("Starting RP2040 physical DMX transmission before node restart")
        rp2040_tool.set_timing(break_us=176, mab_us=16, fps=40)
        rp2040_tool.set_frame(
            [17, 34, 51, 68, 85, 102, 119, 136],
            slots=8,
        )
        rp2040_tool.mode("tx")
        rp2040_tool.tx("start")
        time.sleep(0.3)

        step("Restarting uNode through the REST API")
        status, body = unode_client.post_json("/api/restart")
        assert status == 200, body.decode(errors="replace")

        step("Waiting for node to come back after restart")
        restarted = wait_for_node_restart(
            unode_client,
            previous_boot_count=initial_boot_count,
        )

        step(
            "Node restarted: "
            f"bootCount={restarted['bootCount']}, direction={restarted['direction']}, "
            f"busGuardMode={restarted.get('busGuardMode')}"
        )

        assert int(restarted["busGuardMode"]) == 1
        assert int(restarted["direction"]) == 1

        step("Waiting for physical DMX input activity after Bus Guarding switch")
        status = wait_for_status(
            unode_client,
            lambda data: int(data["direction"]) == 1 and data["dmxActive"] is True,
            timeout=5.0,
            interval=0.2,
        )

        assert int(status["dmxFrames"]) > 0
    finally:
        step("Stopping RP2040 DMX transmission")
        rp2040_tool.idle()
