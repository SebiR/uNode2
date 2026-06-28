from __future__ import annotations

import socket

from artnet_packets import ARTNET_ID, ARTNET_PORT, OP_DMX, make_artdmx
from helpers import configured_port_address, step, wait_for_status
from unode_client import UNodeClient

ARTNET_MAX_BUFFER = 530
ARTNET_PROTOCOL_VERSION = 14


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


def _opcode_bytes(opcode: int) -> bytes:
    return opcode.to_bytes(2, "little")


def _protocol_version_bytes(version: int = ARTNET_PROTOCOL_VERSION) -> bytes:
    return version.to_bytes(2, "big")


def _artdmx_header(
    *,
    universe: int = 0,
    length: int = 2,
    protocol_version: int = ARTNET_PROTOCOL_VERSION,
) -> bytes:
    return (
        ARTNET_ID
        + _opcode_bytes(OP_DMX)
        + _protocol_version_bytes(protocol_version)
        + b"\x01\x00"
        + (universe & 0x7FFF).to_bytes(2, "little")
        + int(length).to_bytes(2, "big")
    )


def _diagnostics(status: dict) -> dict:
    return status["artNetDiagnostics"]


def _wait_for_diagnostic_counter(
    unode_client: UNodeClient,
    counter: str,
    before_count: int,
) -> dict:
    return wait_for_status(
        unode_client,
        lambda data: _diagnostics(data)[counter] > before_count,
    )


def _send_parser_probe(
    unode_ip: str,
    label: str,
    packet: bytes,
    unode_client: UNodeClient,
    counter: str,
) -> dict:
    before = _diagnostics(unode_client.get_json("/api/status"))[counter]

    step(f"Sending parser probe '{label}' expecting {counter} to increment")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, ARTNET_PORT))
    finally:
        sock.close()

    status = _wait_for_diagnostic_counter(
        unode_client,
        counter,
        before,
    )
    count = _diagnostics(status)[counter]
    step(f"Parser diagnostic {counter}: {before} -> {count}")
    return status


def test_parser_diagnostics_count_malformed_udp_packets(
    unode_client: UNodeClient,
    unode_ip: str,
) -> None:
    probes = [
        (
            "oversized UDP packet",
            bytes(ARTNET_MAX_BUFFER + 1),
            "oversizedPackets",
        ),
        (
            "short UDP packet",
            b"Art-Net",
            "shortPackets",
        ),
        (
            "invalid Art-Net ID",
            b"Bad-Net\x00" + _opcode_bytes(OP_DMX),
            "invalidIdPackets",
        ),
        (
            "unsupported protocol version",
            _artdmx_header(protocol_version=ARTNET_PROTOCOL_VERSION - 1)
            + b"\x00\x00",
            "unsupportedProtocolPackets",
        ),
        (
            "malformed ArtDmx length",
            _artdmx_header(length=4) + b"\x01\x02",
            "malformedPackets",
        ),
        (
            "unsupported opcode",
            ARTNET_ID + _opcode_bytes(0x9999),
            "unsupportedOpcodes",
        ),
    ]

    for label, packet, counter in probes:
        _send_parser_probe(
            unode_ip,
            label,
            packet,
            unode_client,
            counter,
        )

    status = unode_client.get_json("/api/status")
    step(
        "Parser diagnostics after probes: "
        f"{_diagnostics(status)}"
    )


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
