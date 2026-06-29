"""Small byte-level Art-Net packet helpers for uNode tests.

These helpers intentionally cover only the packet types needed by the tests.
They are deliberately simple and assert important wire offsets directly in the
unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ARTNET_ID = b"Art-Net\x00"
ARTNET_PORT = 6454
ARTNET_PROTOCOL_VERSION = 14

OP_POLL = 0x2000
OP_POLL_REPLY = 0x2100
OP_DMX = 0x5000
OP_SYNC = 0x5200
OP_ADDRESS = 0x6000
OP_IP_PROG = 0xF800
OP_IP_PROG_REPLY = 0xF900

ARTNET_AC_LED_NORMAL = 0x02
ARTNET_AC_LED_LOCATE = 0x04
ARTNET_AC_CANCEL_MERGE = 0x01
ARTNET_AC_FAIL_RECORD = 0x0C

ARTNET_IP_PROG_COMMAND_ENABLE = 0x80
ARTNET_IP_PROG_COMMAND_DHCP = 0x40
ARTNET_IP_PROG_COMMAND_DEFAULTS = 0x08
ARTNET_IP_PROG_COMMAND_IP = 0x04
ARTNET_IP_PROG_COMMAND_SUBNET = 0x02
ARTNET_IP_PROG_COMMAND_PORT = 0x01
ARTNET_IP_PROG_COMMAND_GATEWAY = 0x10


def _opcode_bytes(opcode: int) -> bytes:
    return opcode.to_bytes(2, "little")


def _protocol_version_bytes() -> bytes:
    return ARTNET_PROTOCOL_VERSION.to_bytes(2, "big")


def make_artpoll(talk_to_me: int = 0x00, priority: int = 0x10) -> bytes:
    """Build a minimal ArtPoll packet."""

    return (
        ARTNET_ID
        + _opcode_bytes(OP_POLL)
        + _protocol_version_bytes()
        + bytes([talk_to_me & 0xFF, priority & 0xFF])
    )


def make_artpollreply_for_subscriber(
    *,
    ip: str,
    net: int = 0,
    subnet: int = 0,
    universe: int = 0,
    short_name: str = "uNode Test",
    long_name: str = "uNode Python Test Subscriber",
) -> bytes:
    """Build a minimal ArtPollReply advertising one Art-Net input port."""

    packet = bytearray(239)
    packet[0:8] = ARTNET_ID
    packet[8:10] = _opcode_bytes(OP_POLL_REPLY)
    packet[10:14] = _ip_bytes(ip)
    packet[14:16] = ARTNET_PORT.to_bytes(2, "little")
    packet[16:18] = bytes([0, 1])
    packet[18] = net & 0x7F
    packet[19] = subnet & 0x0F
    packet[23] = 0xE0
    packet[26:44] = _fixed_c_string(short_name, 18)
    packet[44:108] = _fixed_c_string(long_name, 64)
    packet[108:172] = _fixed_c_string("#0001 [0001] Test Subscriber", 64)
    packet[172:174] = (1).to_bytes(2, "big")
    packet[174] = 0x40  # DMX input port, suitable as an ArtDmx subscriber.
    packet[186] = universe & 0x0F
    packet[211] = 1
    packet[212] = 0x08
    return bytes(packet)


def make_artsync() -> bytes:
    """Build a minimal ArtSync packet."""

    return (
        ARTNET_ID
        + _opcode_bytes(OP_SYNC)
        + _protocol_version_bytes()
        + b"\x00\x00"
    )


def _fixed_c_string(value: str, length: int) -> bytes:
    encoded = value.encode("ascii", errors="replace")[: length - 1]
    return encoded + bytes(length - len(encoded))


def _ip_bytes(address: str) -> bytes:
    parts = address.split(".")
    if len(parts) != 4:
        raise ValueError(f"Invalid IPv4 address: {address}")
    return bytes(int(part) & 0xFF for part in parts)


def _ip_string(data: bytes) -> str:
    if len(data) != 4:
        raise ValueError("IPv4 field must contain exactly four bytes")
    return ".".join(str(part) for part in data)


def make_artaddress(
    *,
    short_name: str = "",
    long_name: str = "",
    command: int = 0,
    bind_index: int = 1,
    net: int = 0,
    subnet: int = 0,
    sw_in: Iterable[int] = (0, 0, 0, 0),
    sw_out: Iterable[int] = (0, 0, 0, 0),
    acn_priority: int = 0,
) -> bytes:
    """Build an ArtAddress packet for the uNode-supported fields."""

    sw_in_bytes = bytes((int(value) & 0xFF) for value in sw_in)
    sw_out_bytes = bytes((int(value) & 0xFF) for value in sw_out)

    if len(sw_in_bytes) != 4:
        raise ValueError("ArtAddress SwIn must contain exactly four values")
    if len(sw_out_bytes) != 4:
        raise ValueError("ArtAddress SwOut must contain exactly four values")

    return (
        ARTNET_ID
        + _opcode_bytes(OP_ADDRESS)
        + _protocol_version_bytes()
        + bytes([net & 0xFF, bind_index & 0xFF])
        + _fixed_c_string(short_name, 18)
        + _fixed_c_string(long_name, 64)
        + sw_in_bytes
        + sw_out_bytes
        + bytes([subnet & 0xFF, acn_priority & 0xFF, command & 0xFF])
    )


def make_artipprog(
    *,
    command: int = 0,
    ip: str = "0.0.0.0",
    subnet: str = "0.0.0.0",
    port: int = ARTNET_PORT,
    gateway: str = "0.0.0.0",
) -> bytes:
    """Build an ArtIpProg packet."""

    return (
        ARTNET_ID
        + _opcode_bytes(OP_IP_PROG)
        + _protocol_version_bytes()
        + b"\x00\x00"
        + bytes([command & 0xFF, 0x00])
        + _ip_bytes(ip)
        + _ip_bytes(subnet)
        + int(port).to_bytes(2, "big")
        + _ip_bytes(gateway)
    )


def make_artdmx(
    universe: int,
    values: Iterable[int],
    *,
    sequence: int = 1,
    physical: int = 0,
) -> bytes:
    """Build one ArtDmx packet for a 15-bit Port-Address."""

    payload = bytes(max(0, min(255, int(value))) for value in values)

    if len(payload) == 0:
        payload = b"\x00\x00"
    elif len(payload) == 1:
        payload += b"\x00"
    elif len(payload) % 2:
        payload += b"\x00"

    if len(payload) > 512:
        raise ValueError("ArtDmx payload may not exceed 512 slots")

    return (
        ARTNET_ID
        + _opcode_bytes(OP_DMX)
        + _protocol_version_bytes()
        + bytes([sequence & 0xFF, physical & 0xFF])
        + (universe & 0x7FFF).to_bytes(2, "little")
        + len(payload).to_bytes(2, "big")
        + payload
    )


def _read_c_string(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("ascii", errors="replace")


@dataclass(frozen=True)
class ArtPollReply:
    ip: str
    port: int
    firmware_version: tuple[int, int]
    net: int
    subnet: int
    oem: int
    status1: int
    esta: int
    short_name: str
    long_name: str
    node_report: str
    num_ports: int
    port_types: bytes
    good_input: bytes
    good_output_a: bytes
    sw_in: bytes
    sw_out: bytes
    status2: int
    good_output_b: bytes
    status3: int
    bind_index: int


@dataclass(frozen=True)
class ArtIpProgReply:
    ip: str
    subnet: str
    port: int
    dhcp: bool
    status: int
    gateway: str


@dataclass(frozen=True)
class ArtDmxPacket:
    universe: int
    sequence: int
    physical: int
    length: int
    values: bytes


def parse_artpollreply(packet: bytes) -> ArtPollReply:
    """Parse the ArtPollReply fields currently asserted by uNode tests."""

    if len(packet) < 239:
        raise ValueError(f"ArtPollReply too short: {len(packet)} bytes")
    if packet[0:8] != ARTNET_ID:
        raise ValueError("Invalid Art-Net ID")
    if int.from_bytes(packet[8:10], "little") != OP_POLL_REPLY:
        raise ValueError("Packet is not ArtPollReply")

    return ArtPollReply(
        ip=".".join(str(part) for part in packet[10:14]),
        port=int.from_bytes(packet[14:16], "little"),
        firmware_version=(packet[16], packet[17]),
        net=packet[18] & 0x7F,
        subnet=packet[19] & 0x0F,
        oem=int.from_bytes(packet[20:22], "big"),
        status1=packet[23],
        esta=int.from_bytes(packet[24:26], "little"),
        short_name=_read_c_string(packet[26:44]),
        long_name=_read_c_string(packet[44:108]),
        node_report=_read_c_string(packet[108:172]),
        num_ports=int.from_bytes(packet[172:174], "big"),
        port_types=packet[174:178],
        good_input=packet[178:182],
        good_output_a=packet[182:186],
        sw_in=packet[186:190],
        sw_out=packet[190:194],
        status2=packet[212],
        good_output_b=packet[213:217],
        status3=packet[217],
        bind_index=packet[211],
    )


def parse_artdmx(packet: bytes) -> ArtDmxPacket:
    """Parse one ArtDmx packet."""

    if len(packet) < 18:
        raise ValueError(f"ArtDmx too short: {len(packet)} bytes")
    if packet[0:8] != ARTNET_ID:
        raise ValueError("Invalid Art-Net ID")
    if int.from_bytes(packet[8:10], "little") != OP_DMX:
        raise ValueError("Packet is not ArtDmx")

    length = int.from_bytes(packet[16:18], "big")
    if len(packet) < 18 + length:
        raise ValueError("ArtDmx payload is truncated")

    return ArtDmxPacket(
        sequence=packet[12],
        physical=packet[13],
        universe=int.from_bytes(packet[14:16], "little") & 0x7FFF,
        length=length,
        values=packet[18 : 18 + length],
    )


def parse_artipprogreply(packet: bytes) -> ArtIpProgReply:
    """Parse the ArtIpProgReply fields currently asserted by uNode tests."""

    if len(packet) < 34:
        raise ValueError(f"ArtIpProgReply too short: {len(packet)} bytes")
    if packet[0:8] != ARTNET_ID:
        raise ValueError("Invalid Art-Net ID")
    if int.from_bytes(packet[8:10], "little") != OP_IP_PROG_REPLY:
        raise ValueError("Packet is not ArtIpProgReply")

    return ArtIpProgReply(
        ip=_ip_string(packet[16:20]),
        subnet=_ip_string(packet[20:24]),
        port=int.from_bytes(packet[24:26], "big"),
        dhcp=(packet[26] & ARTNET_IP_PROG_COMMAND_DHCP) != 0,
        status=packet[26],
        gateway=_ip_string(packet[28:32]),
    )
