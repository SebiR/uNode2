from __future__ import annotations

import pytest

from artnet_packets import (
    ARTNET_ID,
    ARTNET_AC_FAIL_RECORD,
    ARTNET_IP_PROG_COMMAND_DHCP,
    ARTNET_PORT,
    ARTNET_PROTOCOL_VERSION,
    ARTNET_AC_LED_LOCATE,
    OP_ADDRESS,
    OP_POLL_REPLY,
    OP_DMX,
    OP_IP_PROG,
    OP_IP_PROG_REPLY,
    OP_POLL,
    OP_SYNC,
    make_artaddress,
    make_artdmx,
    make_artpollreply_for_subscriber,
    make_artipprog,
    make_artpoll,
    make_artsync,
    parse_artdmx,
    parse_artipprogreply,
    parse_artpollreply,
)


def test_artpoll_wire_format() -> None:
    packet = make_artpoll()

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_POLL
    assert int.from_bytes(packet[10:12], "big") == ARTNET_PROTOCOL_VERSION
    assert packet[12] == 0x00
    assert packet[13] == 0x10
    assert len(packet) == 14


def test_artsync_wire_format() -> None:
    packet = make_artsync()

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_SYNC
    assert int.from_bytes(packet[10:12], "big") == ARTNET_PROTOCOL_VERSION
    assert packet[12:14] == b"\x00\x00"
    assert len(packet) == 14


def test_make_artpollreply_for_subscriber_wire_format() -> None:
    packet = make_artpollreply_for_subscriber(
        ip="2.0.0.99",
        net=1,
        subnet=2,
        universe=3,
    )

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_POLL_REPLY
    assert packet[10:14] == b"\x02\x00\x00\x63"
    assert int.from_bytes(packet[14:16], "little") == ARTNET_PORT
    assert packet[18] == 1
    assert packet[19] == 2
    assert packet[174] == 0x40
    assert packet[186] == 3
    assert packet[211] == 1
    assert len(packet) == 239


def test_artaddress_wire_format() -> None:
    packet = make_artaddress(
        short_name="TestNode",
        long_name="Integration Test Node",
        command=ARTNET_AC_LED_LOCATE,
        bind_index=1,
    )

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_ADDRESS
    assert int.from_bytes(packet[10:12], "big") == ARTNET_PROTOCOL_VERSION
    assert packet[12] == 0
    assert packet[13] == 1
    assert packet[14:22] == b"TestNode"
    assert packet[32:53] == b"Integration Test Node"
    assert packet[96:100] == b"\x00\x00\x00\x00"
    assert packet[100:104] == b"\x00\x00\x00\x00"
    assert packet[104] == 0
    assert packet[106] == ARTNET_AC_LED_LOCATE
    assert len(packet) == 107

    record_packet = make_artaddress(command=ARTNET_AC_FAIL_RECORD)
    assert record_packet[106] == ARTNET_AC_FAIL_RECORD


def test_artipprog_wire_format() -> None:
    packet = make_artipprog(
        command=0x80,
        ip="2.0.0.1",
        subnet="255.255.255.0",
        port=ARTNET_PORT,
        gateway="2.0.0.1",
    )

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_IP_PROG
    assert int.from_bytes(packet[10:12], "big") == ARTNET_PROTOCOL_VERSION
    assert packet[12:14] == b"\x00\x00"
    assert packet[14] == 0x80
    assert packet[16:20] == b"\x02\x00\x00\x01"
    assert packet[20:24] == b"\xff\xff\xff\x00"
    assert int.from_bytes(packet[24:26], "big") == ARTNET_PORT
    assert packet[26:30] == b"\x02\x00\x00\x01"
    assert len(packet) == 30


def test_artdmx_wire_format() -> None:
    packet = make_artdmx(
        0x1234,
        [1, 2, 3],
        sequence=7,
        physical=2,
    )

    assert packet[0:8] == ARTNET_ID
    assert int.from_bytes(packet[8:10], "little") == OP_DMX
    assert int.from_bytes(packet[10:12], "big") == ARTNET_PROTOCOL_VERSION
    assert packet[12] == 7
    assert packet[13] == 2
    assert int.from_bytes(packet[14:16], "little") == 0x1234
    assert int.from_bytes(packet[16:18], "big") == 4
    assert packet[18:22] == b"\x01\x02\x03\x00"

    parsed = parse_artdmx(packet)
    assert parsed.sequence == 7
    assert parsed.physical == 2
    assert parsed.universe == 0x1234
    assert parsed.length == 4
    assert parsed.values == b"\x01\x02\x03\x00"


def test_artdmx_clamps_values_and_rejects_oversized_payload() -> None:
    packet = make_artdmx(1, [-1, 0, 255, 300])
    assert packet[18:22] == b"\x00\x00\xff\xff"

    with pytest.raises(ValueError):
        make_artdmx(1, range(513))


def test_artnet_port_constant_matches_spec() -> None:
    assert ARTNET_PORT == 6454


def test_parse_artpollreply_reads_fixed_offsets() -> None:
    packet = bytearray(239)
    packet[0:8] = ARTNET_ID
    packet[8:10] = OP_POLL_REPLY.to_bytes(2, "little")
    packet[10:14] = bytes([2, 0, 0, 123])
    packet[14:16] = ARTNET_PORT.to_bytes(2, "little")
    packet[16:18] = bytes([0, 18])
    packet[18] = 3
    packet[19] = 2
    packet[20:22] = bytes([0x3A, 0x28])
    packet[23] = 0xE0
    packet[24:26] = bytes([0x73, 0x41])
    packet[26:44] = b"IN_uNode".ljust(18, b"\x00")
    packet[44:108] = b"IllumiNocte uNode".ljust(64, b"\x00")
    packet[108:172] = b"#0001 [0001] uNode Ready".ljust(64, b"\x00")
    packet[172:174] = (1).to_bytes(2, "big")
    packet[174] = 0x80
    packet[182] = 0x80
    packet[190] = 1
    packet[211] = 1
    packet[212] = 0x0B
    packet[217] = 0x28

    reply = parse_artpollreply(bytes(packet))

    assert reply.ip == "2.0.0.123"
    assert reply.port == ARTNET_PORT
    assert reply.firmware_version == (0, 18)
    assert reply.net == 3
    assert reply.subnet == 2
    assert reply.short_name == "IN_uNode"
    assert reply.long_name == "IllumiNocte uNode"
    assert reply.node_report == "#0001 [0001] uNode Ready"
    assert reply.num_ports == 1
    assert reply.port_types[0] == 0x80
    assert reply.good_output_a[0] == 0x80
    assert reply.sw_out[0] == 1
    assert reply.bind_index == 1
    assert reply.status2 == 0x0B
    assert reply.status3 == 0x28


def test_parse_artipprogreply_reads_fixed_offsets() -> None:
    packet = bytearray(34)
    packet[0:8] = ARTNET_ID
    packet[8:10] = OP_IP_PROG_REPLY.to_bytes(2, "little")
    packet[10:12] = ARTNET_PROTOCOL_VERSION.to_bytes(2, "big")
    packet[16:20] = bytes([2, 0, 0, 1])
    packet[20:24] = bytes([255, 255, 255, 0])
    packet[24:26] = ARTNET_PORT.to_bytes(2, "big")
    packet[26] = ARTNET_IP_PROG_COMMAND_DHCP
    packet[28:32] = bytes([2, 0, 0, 1])

    reply = parse_artipprogreply(bytes(packet))

    assert reply.ip == "2.0.0.1"
    assert reply.subnet == "255.255.255.0"
    assert reply.port == ARTNET_PORT
    assert reply.dhcp is True
    assert reply.status == ARTNET_IP_PROG_COMMAND_DHCP
    assert reply.gateway == "2.0.0.1"
