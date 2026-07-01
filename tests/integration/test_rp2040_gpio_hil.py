from __future__ import annotations

import os

import pytest

from helpers import step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


def _configured_button_gpio_pin() -> int | None:
    value = os.environ.get("UNODE_BUTTON_GPIO_PIN", "").strip()
    if not value:
        return None
    return int(value, 0)


def _configured_reset_gpio_pin() -> int | None:
    value = os.environ.get("UNODE_RESET_GPIO_PIN", "").strip()
    if not value:
        return None
    return int(value, 0)


def test_rp2040_aux_gpio_json_commands(
    rp2040_tool: Rp2040DmxTool,
) -> None:
    ping = rp2040_tool.ping()
    pins = ping.get("auxGpioPins") or []
    assert pins, "RP2040 tool did not advertise auxiliary GPIO pins"

    pin = int(pins[-1])
    step(f"Testing RP2040 AUX GPIO command support on GPIO{pin}")

    try:
        high = rp2040_tool.gpio_write(pin, 1)
        assert high["pin"] == pin
        assert int(high["value"]) == 1
        assert int(rp2040_tool.gpio_read(pin)["value"]) == 1

        low = rp2040_tool.gpio_write(pin, 0)
        assert low["pin"] == pin
        assert int(low["value"]) == 0
        assert int(rp2040_tool.gpio_read(pin)["value"]) == 0

        pulse = rp2040_tool.gpio_pulse(
            pin,
            value=0,
            duration_ms=20,
        )
        assert pulse["pin"] == pin
        assert pulse["released"] is True
    finally:
        rp2040_tool.gpio_release(pin)


def test_rp2040_gpio_can_toggle_unode_local_button_locate(
    unode_client: UNodeClient,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    pin = _configured_button_gpio_pin()
    if pin is None:
        pytest.skip(
            "Set UNODE_BUTTON_GPIO_PIN to the RP2040 AUX GPIO wired to the "
            "uNode active-low button input"
        )

    config = preserved_config.copy()
    config["buttonAction"] = 1  # Toggle Locate

    step(f"Configuring local button action and using RP2040 GPIO{pin} as button pull-down")
    response = unode_client.save_config(config)
    assert response.get("restartRequired") is False

    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("buttonAction", -1)) == 1,
    )
    initial_locate = bool(status.get("squawking", False))

    try:
        rp2040_tool.gpio_release(pin)

        step("Pulsing active-low button input for 300 ms")
        rp2040_tool.gpio_pulse(
            pin,
            value=0,
            duration_ms=300,
            release=True,
        )

        toggled = wait_for_status(
            unode_client,
            lambda data: bool(data.get("squawking", False)) != initial_locate,
            timeout=3.0,
        )
        assert bool(toggled["squawking"]) != initial_locate
    finally:
        rp2040_tool.gpio_release(pin)


def test_rp2040_gpio_can_reset_unode_and_observe_boot_count(
    unode_client: UNodeClient,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    pin = _configured_reset_gpio_pin()
    if pin is None:
        pytest.skip(
            "Set UNODE_RESET_GPIO_PIN to the RP2040 AUX GPIO wired to the "
            "uNode active-low reset input"
        )

    before = unode_client.get_json("/api/status")
    initial_boot_count = int(before["bootCount"])

    try:
        rp2040_tool.gpio_release(pin)

        step(
            f"Pulsing active-low uNode reset input via RP2040 GPIO{pin} "
            f"from bootCount={initial_boot_count}"
        )
        rp2040_tool.gpio_pulse(
            pin,
            value=0,
            duration_ms=250,
            release=True,
        )

        restarted = wait_for_status(
            unode_client,
            lambda data: int(data.get("bootCount", initial_boot_count))
            > initial_boot_count,
            timeout=25.0,
            interval=0.5,
        )
        assert int(restarted["bootCount"]) > initial_boot_count
    finally:
        rp2040_tool.gpio_release(pin)
