from __future__ import annotations

import time

from artnet_packets import make_artdmx
from helpers import configured_port_address, send_artnet_packet, step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


def _wait_for_rp2040_frame_values(
    tool: Rp2040DmxTool,
    expected: list[int],
    *,
    timeout: float = 4.0,
) -> dict:
    deadline = time.time() + timeout
    last_frame = {}

    while time.time() < deadline:
        last_frame = tool.get_frame(start=1, count=len(expected))
        if last_frame.get("values") == expected:
            return last_frame
        time.sleep(0.1)

    raise AssertionError(
        f"Timed out waiting for RP2040 DMX values {expected}; last={last_frame}"
    )


def test_artnet_to_dmx_output_reaches_rp2040_analyzer(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to Art-Net -> DMX for hardware DMX output test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 0
        and int(data["universe"]) == universe,
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    expected = [7, 23, 42, 99, 128, 201]
    packet = make_artdmx(
        universe,
        expected,
        sequence=31,
    )

    step(f"Sending ArtDmx to uNode Port-Address {universe}: {expected}")
    for _index in range(4):
        send_artnet_packet(unode_ip, packet)
        time.sleep(0.05)

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        expected,
    )
    step(
        "RP2040 analyzer saw expected DMX values: "
        f"slots={frame['slots']}, values={frame['values']}"
    )

    stats = rp2040_tool.get_stats()
    step(
        "RP2040 analyzer stats: "
        f"frames={stats['frames']}, fps={stats['fps']}, "
        f"lastBreakUs={stats['lastBreakUs']}, lastMabUs={stats['lastMabUs']}"
    )

    assert stats["frames"] > 0
    assert stats["lastSlots"] >= len(expected)
