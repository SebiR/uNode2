from __future__ import annotations

import os
import time

import pytest

from artnet_packets import (
    ARTNET_AC_LED_LOCATE,
    ARTNET_AC_LED_NORMAL,
    make_artaddress,
    make_artdmx,
)
from helpers import (
    configured_port_address,
    request_artpoll_reply,
    send_artnet_packet,
    step,
    wait_for_status,
)
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


BUTTON_LONG_PRESS_MS = 2300
BUTTON_RELEASE_SETTLE_SECONDS = 0.3


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


def _long_press_and_release_button(
    tool: Rp2040DmxTool,
    pin: int,
) -> None:
    """Hold the active-low button, then allow its release to debounce."""
    tool.gpio_pulse(
        pin,
        value=0,
        duration_ms=BUTTON_LONG_PRESS_MS,
        release=True,
    )
    # The uNode uses a 200 ms debounce interval. Without this explicit release
    # window, a following pulse can begin before the firmware observes the
    # released state and both pulses are interpreted as one continuous press.
    time.sleep(BUTTON_RELEASE_SETTLE_SECONDS)


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
    unode_ip: str,
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
    config["buttonShortAction"] = 1  # Toggle Locate
    config["buttonLongAction"] = 0  # Disabled

    step(f"Configuring short button action and using RP2040 GPIO{pin} as button pull-down")
    response = unode_client.save_config(config)
    assert response.get("restartRequired") is False

    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("buttonShortAction", -1)) == 1,
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
        step("Restoring Locate state after local button test")
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                command=(
                    ARTNET_AC_LED_LOCATE
                    if initial_locate
                    else ARTNET_AC_LED_NORMAL
                ),
                bind_index=1,
            ),
        )
        wait_for_status(
            unode_client,
            lambda data: bool(data.get("squawking", False)) == initial_locate,
            timeout=3.0,
        )


def test_rp2040_gpio_long_press_toggles_unode_led_mute(
    unode_client: UNodeClient,
    unode_ip: str,
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
    config["buttonShortAction"] = 0  # Disabled
    config["buttonLongAction"] = 2  # Toggle LED Mute

    step(f"Configuring long button action and using RP2040 GPIO{pin} as button pull-down")
    response = unode_client.save_config(config)
    assert response.get("restartRequired") is False

    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("buttonLongAction", -1)) == 2,
    )
    assert status.get("ledMuted") is False

    try:
        rp2040_tool.gpio_release(pin)

        step("Holding active-low button input for 2300 ms to enable LED mute")
        _long_press_and_release_button(rp2040_tool, pin)

        muted = wait_for_status(
            unode_client,
            lambda data: data.get("ledMuted") is True,
            timeout=3.0,
        )
        assert muted["ledMuted"] is True

        step("Holding active-low button input again to disable LED mute")
        _long_press_and_release_button(rp2040_tool, pin)

        unmuted = wait_for_status(
            unode_client,
            lambda data: data.get("ledMuted") is False,
            timeout=3.0,
        )
        assert unmuted["ledMuted"] is False

        step("Muting once more and clearing LED mute via ArtAddress Normal")
        _long_press_and_release_button(rp2040_tool, pin)
        wait_for_status(
            unode_client,
            lambda data: data.get("ledMuted") is True,
            timeout=3.0,
        )
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                command=ARTNET_AC_LED_NORMAL,
                bind_index=1,
            ),
        )
        artnet_unmuted = wait_for_status(
            unode_client,
            lambda data: data.get("ledMuted") is False,
            timeout=3.0,
        )
        assert artnet_unmuted["ledMuted"] is False
    finally:
        rp2040_tool.gpio_release(pin)
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                command=ARTNET_AC_LED_NORMAL,
                bind_index=1,
            ),
        )


def test_rp2040_gpio_can_reset_unode_and_observe_boot_count(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
    record_property,
) -> None:
    pin = _configured_reset_gpio_pin()
    if pin is None:
        pytest.skip(
            "Set UNODE_RESET_GPIO_PIN to the RP2040 AUX GPIO wired to the "
            "uNode active-low reset input"
        )

    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> physical DMX
    config["liveProtocol"] = 0
    config["busGuardMode"] = 0
    step("Preparing Art-Net -> DMX profile for post-reset functional check")
    unode_client.save_config(config)
    port_address = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("direction", -1)) == 0
        and int(data.get("liveProtocol", -1)) == 0
        and int(data.get("universe", -1)) == port_address,
    )

    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    before = unode_client.get_json("/api/status")
    initial_boot_count = int(before["bootCount"])
    started = time.perf_counter()

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
        api_recovery_ms = (time.perf_counter() - started) * 1000.0
        step(
            "Node HTTP/API recovered after "
            f"{api_recovery_ms:.0f} ms: bootCount={restarted['bootCount']}, "
            f"resetReason='{restarted.get('resetReason', 'N/A')}'"
        )

        reply = request_artpoll_reply(unode_ip, timeout=5.0)
        artpoll_recovery_ms = (time.perf_counter() - started) * 1000.0
        assert reply.net == int(config["net"])
        assert reply.subnet == int(config["subnetId"])
        assert reply.sw_out[0] == int(config["universe"])
        step(f"ArtPollReply recovered after {artpoll_recovery_ms:.0f} ms")

        expected = [17, 51, 85, 119, 153, 187]
        rp2040_tool.begin_wait_frame(expected, timeout_ms=3000)
        packet = make_artdmx(
            port_address,
            expected,
            sequence=73,
        )
        for _attempt in range(5):
            send_artnet_packet(unode_ip, packet)
            time.sleep(0.05)
        wait_result = rp2040_tool.finish_wait_frame(timeout_ms=3000)
        assert wait_result.get("matched") is True
        dmx_recovery_ms = (time.perf_counter() - started) * 1000.0
        step(
            "Post-reset Art-Net -> physical DMX conversion verified after "
            f"{dmx_recovery_ms:.0f} ms"
        )

        record_property(
            "metric.resetRecovery",
            {
                "gpio": pin,
                "pulseMs": 250,
                "apiRecoveryMs": round(api_recovery_ms, 1),
                "artPollRecoveryMs": round(artpoll_recovery_ms, 1),
                "dmxRecoveryMs": round(dmx_recovery_ms, 1),
                "bootCountBefore": initial_boot_count,
                "bootCountAfter": int(restarted["bootCount"]),
                "resetReason": restarted.get("resetReason", ""),
            },
        )
    finally:
        rp2040_tool.gpio_release(pin)
