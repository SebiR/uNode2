from __future__ import annotations

import socket
import time

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


def _send_sequenced_artdmx(
    unode_ip: str,
    universe: int,
    values: list[int],
    *,
    sequence: int,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(
            make_artdmx(
                universe,
                values,
                sequence=sequence,
            ),
            (unode_ip, ARTNET_PORT),
        )
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


def _get_status_with_retry(unode_client: UNodeClient) -> dict:
    last_error: Exception | None = None

    for _attempt in range(5):
        try:
            return unode_client.get_json("/api/status")
        except Exception as error:
            last_error = error
            time.sleep(0.1)

    raise AssertionError("Could not read /api/status after retries") from last_error


def _wait_for_diagnostic_counter(
    unode_client: UNodeClient,
    counter: str,
    before_count: int,
) -> dict:
    deadline = time.time() + 3.0
    last_status = {}

    while time.time() < deadline:
        last_status = _get_status_with_retry(unode_client)
        if _diagnostics(last_status)[counter] > before_count:
            return last_status
        time.sleep(0.1)

    raise AssertionError(
        f"Timed out waiting for diagnostic counter {counter}; last={last_status}"
    )


def _send_parser_probe(
    unode_ip: str,
    label: str,
    packet: bytes,
    unode_client: UNodeClient,
    counter: str,
) -> dict:
    before = _diagnostics(_get_status_with_retry(unode_client))[counter]

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
    config["liveProtocol"] = 0
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


def test_artdmx_in_sacn_mode_increments_protocol_drop_counter(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Protocol -> DMX
    config["liveProtocol"] = 1  # sACN live data, ArtDmx should be rejected.
    if configured_port_address(config) == 0:
        config["universe"] = 1

    step("Switching node to sACN live protocol before ArtDmx protocol-drop test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 1
        and int(data["direction"]) == 0,
    )

    before = unode_client.get_json("/api/status")
    before_drops = int(before["artNetDiagnostics"].get("protocolDrops", 0))
    before_packets = int(before["artnetPackets"])

    step("Sending ArtDmx while sACN live data is selected")
    _send_artdmx(unode_ip, universe, [1, 2, 3, 4])

    status = wait_for_status(
        unode_client,
        lambda data: int(data["artNetDiagnostics"].get("protocolDrops", 0))
        > before_drops,
    )

    assert int(status["artnetPackets"]) == before_packets


def test_artdmx_sequence_drops_duplicate_and_out_of_order_packets(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["liveProtocol"] = 0
    step("Switching node to Art-Net -> DMX for ArtDmx sequence test")
    unode_client.save_config(config)
    universe = configured_port_address(config)

    before = unode_client.get_json("/api/status")
    before_packets = before["artnetPackets"]
    before_drops = _diagnostics(before)["sequenceDrops"]

    step("Sending initial ArtDmx sequence 10; it should be accepted")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [10, 10, 10, 10],
        sequence=10,
    )
    accepted = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > before_packets,
    )
    accepted_packets = accepted["artnetPackets"]

    step("Sending duplicate ArtDmx sequence 10; it should be dropped")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [20, 20, 20, 20],
        sequence=10,
    )
    duplicate = wait_for_status(
        unode_client,
        lambda data: _diagnostics(data)["sequenceDrops"] > before_drops,
    )
    duplicate_drops = _diagnostics(duplicate)["sequenceDrops"]
    assert duplicate["artnetPackets"] == accepted_packets

    step("Sending older ArtDmx sequence 9; it should also be dropped")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [30, 30, 30, 30],
        sequence=9,
    )
    older = wait_for_status(
        unode_client,
        lambda data: _diagnostics(data)["sequenceDrops"] > duplicate_drops,
    )
    assert older["artnetPackets"] == accepted_packets

    step("Sending newer ArtDmx sequence 11; it should be accepted")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [40, 40, 40, 40],
        sequence=11,
    )
    newer = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > accepted_packets,
    )

    step(
        "ArtDmx sequence diagnostics: "
        f"drops {before_drops} -> {_diagnostics(newer)['sequenceDrops']}, "
        f"packets {before_packets} -> {newer['artnetPackets']}"
    )
    assert _diagnostics(newer)["sequenceDrops"] >= before_drops + 2


def test_artdmx_sequence_zero_disables_sequence_filter_and_wraparound_is_newer(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["liveProtocol"] = 0
    step("Switching node to Art-Net -> DMX for sequence-zero/wrap test")
    unode_client.save_config(config)
    universe = configured_port_address(config)

    before = unode_client.get_json("/api/status")
    before_packets = before["artnetPackets"]
    before_drops = _diagnostics(before)["sequenceDrops"]

    step("Sending ArtDmx sequence 100 to establish sequence state")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [1, 1, 1, 1],
        sequence=100,
    )
    first = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > before_packets,
    )

    step("Sending ArtDmx sequence 0; sequencing is disabled and accepted")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [2, 2, 2, 2],
        sequence=0,
    )
    zero = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > first["artnetPackets"],
    )
    assert _diagnostics(zero)["sequenceDrops"] == before_drops

    step("Sending ArtDmx sequence 254 after sequence 0 reset; accepted")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [3, 3, 3, 3],
        sequence=254,
    )
    reset_accept = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > zero["artnetPackets"],
    )

    step("Sending ArtDmx sequence 255 then 1 to verify wraparound acceptance")
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [4, 4, 4, 4],
        sequence=255,
    )
    wrap_start = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > reset_accept["artnetPackets"],
    )
    _send_sequenced_artdmx(
        unode_ip,
        universe,
        [5, 5, 5, 5],
        sequence=1,
    )
    wrap_end = wait_for_status(
        unode_client,
        lambda data: data["artnetPackets"] > wrap_start["artnetPackets"],
    )

    step(
        "ArtDmx sequence-zero/wrap diagnostics: "
        f"drops stayed at {_diagnostics(wrap_end)['sequenceDrops']}, "
        f"packets {before_packets} -> {wrap_end['artnetPackets']}"
    )
    assert _diagnostics(wrap_end)["sequenceDrops"] == before_drops
