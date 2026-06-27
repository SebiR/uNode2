from __future__ import annotations

import socket

from artnet_packets import ARTNET_PORT, make_artdmx
from helpers import configured_port_address, step, wait_for_status
from unode_client import UNodeClient


def _send_artdmx(unode_ip: str, universe: int, values: list[int]) -> None:
    packet = make_artdmx(
        universe,
        values,
        sequence=1,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, ARTNET_PORT))
    finally:
        sock.close()


def test_wrong_universe_warning_clears_after_valid_artdmx(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    step("Switching node to Art-Net -> DMX for diagnostics test")
    unode_client.save_config(config)

    configured_universe = configured_port_address(config)
    wrong_universe = (configured_universe + 1) & 0x7FFF
    if wrong_universe == configured_universe:
        wrong_universe = (configured_universe + 2) & 0x7FFF

    before = unode_client.get_json("/api/status")
    before_count = before["artNetDiagnostics"]["wrongUniversePackets"]

    step(
        f"Sending ArtDmx to wrong Port-Address {wrong_universe} "
        f"(configured {configured_universe})"
    )
    _send_artdmx(unode_ip, wrong_universe, [1, 2, 3, 4])

    status = wait_for_status(
        unode_client,
        lambda data: data["artNetDiagnostics"]["wrongUniversePackets"] > before_count
        and data["artNetDiagnostics"]["lastWrongUniverse"] == wrong_universe
        and data["artNetDiagnostics"]["wrongUniverseWarningActive"],
    )

    step(
        "Wrong-universe warning active: "
        f"counter={status['artNetDiagnostics']['wrongUniversePackets']}, "
        f"last={status['artNetDiagnostics']['lastWrongUniverse']}"
    )
    assert status["artNetDiagnostics"]["wrongUniverseWarningActive"] is True

    step(f"Sending valid ArtDmx to Port-Address {configured_universe}")
    _send_artdmx(unode_ip, configured_universe, [10, 20, 30, 40])

    status = wait_for_status(
        unode_client,
        lambda data: not data["artNetDiagnostics"]["wrongUniverseWarningActive"],
    )

    step("Wrong-universe warning cleared after valid ArtDmx")
    assert status["artNetDiagnostics"]["wrongUniversePackets"] > before_count
