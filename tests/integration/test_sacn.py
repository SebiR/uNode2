from __future__ import annotations

import socket

from helpers import configured_port_address, step, wait_for_status
from sacn_packets import SACN_PORT, make_sacn_dmx
from unode_client import UNodeClient


def _send_sacn_unicast(unode_ip: str, packet: bytes) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, SACN_PORT))
    finally:
        sock.close()


def test_sacn_live_protocol_accepts_data_packet(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = 1
    if configured_port_address(config) == 0:
        config["universe"] = 1

    universe = configured_port_address(config)

    step(f"Switching node to sACN live protocol on Universe {universe}")
    response = unode_client.save_config(config)
    assert response.get("appliedLive") is True
    assert response.get("restartRequired") is False

    before = unode_client.get_json("/api/status")
    before_packets = int(before.get("sacnPackets", 0))

    step("Sending one valid sACN Data Packet to UDP 5568")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            values=[11, 22, 33, 44],
        ),
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 1
        and int(data.get("sacnPackets", 0)) > before_packets
        and data.get("sacnActive") is True,
        timeout=3.0,
    )

    step(
        "sACN accepted: "
        f"packets={status.get('sacnPackets')}, "
        f"fps={status.get('sacnFPS')}, "
        f"last={status.get('lastSacnPacketAge')} ms"
    )

    assert int(status["sacnUniverse"]) == universe


def test_sacn_wrong_universe_increments_diagnostic_counter(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = 1
    if configured_port_address(config) == 0:
        config["universe"] = 1

    universe = configured_port_address(config)
    wrong_universe = universe + 1 if universe < 63999 else universe - 1

    step(
        "Switching node to sACN live protocol and sending a wrong-Universe packet"
    )
    response = unode_client.save_config(config)
    assert response.get("appliedLive") is True
    assert response.get("restartRequired") is False

    before = unode_client.get_json("/api/status")
    diagnostics = before.get("sacnDiagnostics", {})
    before_wrong = int(diagnostics.get("wrongUniversePackets", 0))

    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=wrong_universe,
            sequence=1,
            values=[1, 2],
        ),
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(
            data.get("sacnDiagnostics", {}).get("wrongUniversePackets", 0)
        )
        > before_wrong,
        timeout=3.0,
    )

    diagnostics = status["sacnDiagnostics"]
    assert int(diagnostics["lastWrongUniverse"]) == wrong_universe
