from __future__ import annotations

import socket
import uuid

from helpers import configured_port_address, step, wait_for_status
from sacn_packets import SACN_PORT, make_sacn_dmx
from unode_client import UNodeClient


CID_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001").bytes
CID_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002").bytes


def _send_sacn_unicast(unode_ip: str, packet: bytes) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, SACN_PORT))
    finally:
        sock.close()


def _mutated_packet(packet: bytes, offset: int, value: int) -> bytes:
    data = bytearray(packet)
    data[offset] = value & 0xFF
    return bytes(data)


def _configure_sacn_output(
    unode_client: UNodeClient,
    preserved_config: dict,
) -> tuple[dict, int]:
    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = 1
    if configured_port_address(config) == 0:
        config["universe"] = 1

    reset_config = config.copy()
    reset_config["liveProtocol"] = 0

    step("Resetting sACN runtime state via temporary Art-Net live protocol")
    unode_client.save_config(reset_config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 0,
    )

    universe = configured_port_address(config)
    step(f"Switching node to sACN live protocol on Universe {universe}")
    response = unode_client.save_config(config)
    assert response.get("appliedLive") is True
    assert response.get("restartRequired") is False

    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 1
        and int(data["direction"]) == 0
        and int(data["sacnUniverse"]) == universe,
    )

    return config, universe


def test_sacn_live_protocol_accepts_data_packet(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

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
    _config, universe = _configure_sacn_output(unode_client, preserved_config)
    wrong_universe = universe + 1 if universe < 63999 else universe - 1

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


def test_sacn_malformed_packets_increment_diagnostic_counter(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

    before = unode_client.get_json("/api/status")
    before_malformed = int(before["sacnDiagnostics"]["malformedPackets"])

    probes = [
        ("short packet", b"ASC"),
        (
            "bad ACN packet identifier",
            _mutated_packet(
                make_sacn_dmx(
                    universe=universe,
                    sequence=1,
                    values=[1, 2],
                ),
                4,
                ord("X"),
            ),
        ),
        (
            "non-zero start code",
            _mutated_packet(
                make_sacn_dmx(
                    universe=universe,
                    sequence=2,
                    values=[1, 2],
                ),
                125,
                1,
            ),
        ),
    ]

    for label, packet in probes:
        step(f"Sending malformed sACN probe: {label}")
        _send_sacn_unicast(unode_ip, packet)

    status = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["malformedPackets"])
        >= before_malformed + len(probes),
        timeout=3.0,
    )

    step(
        "sACN malformed diagnostics: "
        f"{before_malformed} -> {status['sacnDiagnostics']['malformedPackets']}"
    )


def test_sacn_valid_packet_in_artnet_mode_increments_protocol_drop_counter(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = 0
    if configured_port_address(config) == 0:
        config["universe"] = 1

    universe = configured_port_address(config)
    step("Switching node to Art-Net live protocol before sACN protocol-drop test")
    unode_client.save_config(config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 0
        and int(data["direction"]) == 0,
    )

    before = unode_client.get_json("/api/status")
    before_drops = int(before["sacnDiagnostics"]["protocolDrops"])

    step("Sending valid sACN while Art-Net live data is selected")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            values=[1, 2, 3, 4],
        ),
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["protocolDrops"]) > before_drops,
        timeout=3.0,
    )
    assert int(status["sacnPackets"]) == int(before["sacnPackets"])


def test_sacn_valid_packet_in_dmx_input_mode_increments_direction_drop_counter(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 1
    config["liveProtocol"] = 1
    if configured_port_address(config) == 0:
        config["universe"] = 1

    universe = configured_port_address(config)
    step("Switching node to DMX input before sACN direction-drop test")
    unode_client.save_config(config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 1
        and int(data["direction"]) == 1,
    )

    before = unode_client.get_json("/api/status")
    before_drops = int(before["sacnDiagnostics"]["directionDrops"])

    step("Sending valid sACN while node is configured for DMX input")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            values=[1, 2, 3, 4],
        ),
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["directionDrops"]) > before_drops,
        timeout=3.0,
    )
    assert int(status["sacnPackets"]) == int(before["sacnPackets"])


def test_sacn_sequence_drops_duplicate_and_out_of_order_packets(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

    before = unode_client.get_json("/api/status")
    before_packets = int(before.get("sacnPackets", 0))
    before_drops = int(before["sacnDiagnostics"]["sequenceDrops"])

    step("Sending initial sACN sequence 10; it should be accepted")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=10,
            values=[10, 10, 10, 10],
            cid=CID_A,
        ),
    )
    accepted = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > before_packets,
    )
    accepted_packets = int(accepted["sacnPackets"])

    step("Sending duplicate sACN sequence 10; it should be dropped")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=10,
            values=[20, 20, 20, 20],
            cid=CID_A,
        ),
    )
    duplicate = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["sequenceDrops"]) > before_drops,
    )
    duplicate_drops = int(duplicate["sacnDiagnostics"]["sequenceDrops"])
    assert int(duplicate["sacnPackets"]) == accepted_packets

    step("Sending older sACN sequence 9; it should also be dropped")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=9,
            values=[30, 30, 30, 30],
            cid=CID_A,
        ),
    )
    older = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["sequenceDrops"])
        > duplicate_drops,
    )
    assert int(older["sacnPackets"]) == accepted_packets

    step("Sending newer sACN sequence 11; it should be accepted")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=11,
            values=[40, 40, 40, 40],
            cid=CID_A,
        ),
    )
    newer = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > accepted_packets,
    )

    step(
        "sACN sequence diagnostics: "
        f"drops {before_drops} -> {newer['sacnDiagnostics']['sequenceDrops']}, "
        f"packets {before_packets} -> {newer['sacnPackets']}"
    )
    assert int(newer["sacnDiagnostics"]["sequenceDrops"]) >= before_drops + 2


def test_sacn_sequence_accepts_wraparound_as_newer(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

    before = unode_client.get_json("/api/status")
    before_packets = int(before.get("sacnPackets", 0))
    before_drops = int(before["sacnDiagnostics"]["sequenceDrops"])

    for sequence, values in [
        (254, [1, 1, 1, 1]),
        (255, [2, 2, 2, 2]),
        (1, [3, 3, 3, 3]),
    ]:
        step(f"Sending sACN sequence {sequence}; it should be accepted")
        _send_sacn_unicast(
            unode_ip,
            make_sacn_dmx(
                universe=universe,
                sequence=sequence,
                values=values,
                cid=CID_A,
            ),
        )
        wait_for_status(
            unode_client,
            lambda data, minimum=before_packets + 1: int(
                data.get("sacnPackets", 0)
            )
            >= minimum,
        )
        before_packets += 1

    status = unode_client.get_json("/api/status")
    step(
        "sACN wraparound diagnostics: "
        f"packets={status['sacnPackets']}, "
        f"sequenceDrops={status['sacnDiagnostics']['sequenceDrops']}"
    )
    assert int(status["sacnDiagnostics"]["sequenceDrops"]) == before_drops


def test_sacn_priority_drops_lower_priority_source_while_higher_source_is_active(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

    before = unode_client.get_json("/api/status")
    before_packets = int(before.get("sacnPackets", 0))
    before_priority_drops = int(before["sacnDiagnostics"]["priorityDrops"])

    step("Sending lower-priority sACN source A; it should be accepted")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            priority=90,
            values=[1, 2, 3, 4],
            cid=CID_A,
            source_name="uNode pytest low",
        ),
    )
    source_a = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > before_packets,
    )

    step("Sending higher-priority sACN source B; it should take over")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            priority=120,
            values=[11, 22, 33, 44],
            cid=CID_B,
            source_name="uNode pytest high",
        ),
    )
    source_b = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0))
        > int(source_a["sacnPackets"]),
    )

    step("Sending source A again below active highest priority; it should drop")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=2,
            priority=90,
            values=[5, 6, 7, 8],
            cid=CID_A,
            source_name="uNode pytest low",
        ),
    )
    dropped = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["priorityDrops"])
        > before_priority_drops,
    )
    assert int(dropped["sacnPackets"]) == int(source_b["sacnPackets"])

    step("Sending source B with next sequence; it should still be accepted")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=2,
            priority=120,
            values=[12, 23, 34, 45],
            cid=CID_B,
            source_name="uNode pytest high",
        ),
    )
    accepted = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0))
        > int(source_b["sacnPackets"]),
    )

    step(
        "sACN priority diagnostics: "
        f"priorityDrops {before_priority_drops} -> "
        f"{accepted['sacnDiagnostics']['priorityDrops']}, "
        f"packets {before_packets} -> {accepted['sacnPackets']}"
    )


def test_sacn_stream_terminated_releases_high_priority_source(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_sacn_output(unode_client, preserved_config)

    before = unode_client.get_json("/api/status")
    before_packets = int(before.get("sacnPackets", 0))
    before_terminated = int(before["sacnDiagnostics"]["streamTerminated"])

    step("Sending high-priority source B; it should be accepted")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            priority=120,
            values=[101, 102, 103, 104],
            cid=CID_B,
            source_name="uNode pytest high",
        ),
    )
    high = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > before_packets,
    )

    step("Sending Stream_Terminated from source B")
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=2,
            priority=120,
            values=[101, 102, 103, 104],
            cid=CID_B,
            source_name="uNode pytest high",
            options=0x40,
        ),
    )
    terminated = wait_for_status(
        unode_client,
        lambda data: int(data["sacnDiagnostics"]["streamTerminated"])
        > before_terminated,
    )
    assert int(terminated["sacnPackets"]) == int(high["sacnPackets"])

    step(
        "Sending lower-priority source A after termination; it should now be accepted"
    )
    _send_sacn_unicast(
        unode_ip,
        make_sacn_dmx(
            universe=universe,
            sequence=1,
            priority=90,
            values=[1, 2, 3, 4],
            cid=CID_A,
            source_name="uNode pytest low",
        ),
    )
    accepted = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > int(high["sacnPackets"]),
    )

    step(
        "sACN Stream_Terminated released priority lock: "
        f"streamTerminated={accepted['sacnDiagnostics']['streamTerminated']}, "
        f"packets={accepted['sacnPackets']}"
    )
