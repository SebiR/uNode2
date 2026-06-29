from __future__ import annotations

import uuid
from dataclasses import dataclass

SACN_PORT = 5568
ACN_PACKET_IDENTIFIER = b"ASC-E1.17\x00\x00\x00"


@dataclass(frozen=True)
class SacnDmxPacket:
    cid: bytes
    source_name: str
    priority: int
    sequence: int
    options: int
    universe: int
    start_code: int
    values: bytes


def sacn_multicast_address(universe: int) -> str:
    if universe < 1 or universe > 63999:
        raise ValueError("sACN universe must be between 1 and 63999")

    return f"239.255.{(universe >> 8) & 0xff}.{universe & 0xff}"


def _put16(value: int) -> bytes:
    return int(value).to_bytes(2, "big")


def _put32(value: int) -> bytes:
    return int(value).to_bytes(4, "big")


def make_sacn_dmx(
    *,
    universe: int = 1,
    values: bytes | list[int] = b"",
    sequence: int = 1,
    priority: int = 100,
    source_name: str = "uNode test",
    cid: bytes | None = None,
    options: int = 0,
) -> bytes:
    if universe < 1 or universe > 63999:
        raise ValueError("sACN universe must be between 1 and 63999")

    payload = bytes(values)
    if len(payload) > 512:
        raise ValueError("sACN DMX payload must not exceed 512 slots")

    cid_bytes = cid or uuid.UUID("12345678-1234-5678-1234-567812345678").bytes
    if len(cid_bytes) != 16:
        raise ValueError("CID must contain 16 bytes")

    property_count = len(payload) + 1
    packet_length = 126 + len(payload)
    packet = bytearray(packet_length)

    packet[0:2] = _put16(0x0010)
    packet[2:4] = _put16(0x0000)
    packet[4:16] = ACN_PACKET_IDENTIFIER

    packet[16:18] = _put16(0x7000 | (packet_length - 16))
    packet[18:22] = _put32(0x00000004)
    packet[22:38] = cid_bytes

    packet[38:40] = _put16(0x7000 | (packet_length - 38))
    packet[40:44] = _put32(0x00000002)
    encoded_name = source_name.encode("ascii", errors="replace")[:63]
    packet[44 : 44 + len(encoded_name)] = encoded_name
    packet[108] = priority & 0xff
    packet[109:111] = _put16(0)
    packet[111] = sequence & 0xff
    packet[112] = options & 0xff
    packet[113:115] = _put16(universe)

    packet[115:117] = _put16(0x7000 | (packet_length - 115))
    packet[117] = 0x02
    packet[118] = 0xA1
    packet[119:121] = _put16(0)
    packet[121:123] = _put16(1)
    packet[123:125] = _put16(property_count)
    packet[125] = 0
    packet[126:] = payload

    return bytes(packet)


def _read16(packet: bytes, offset: int) -> int:
    return int.from_bytes(packet[offset : offset + 2], "big")


def _read32(packet: bytes, offset: int) -> int:
    return int.from_bytes(packet[offset : offset + 4], "big")


def _pdu_length(packet: bytes, offset: int) -> int:
    return _read16(packet, offset) & 0x0FFF


def parse_sacn_dmx(packet: bytes) -> SacnDmxPacket:
    if len(packet) < 126:
        raise ValueError("sACN packet is too short")

    if _read16(packet, 0) != 0x0010 or _read16(packet, 2) != 0:
        raise ValueError("invalid sACN preamble")

    if packet[4:16] != ACN_PACKET_IDENTIFIER:
        raise ValueError("invalid ACN packet identifier")

    if _read32(packet, 18) != 0x00000004:
        raise ValueError("unsupported root vector")

    if _read32(packet, 40) != 0x00000002:
        raise ValueError("unsupported framing vector")

    if packet[117] != 0x02 or packet[118] != 0xA1:
        raise ValueError("unsupported DMP vector or address type")

    property_count = _read16(packet, 123)
    if property_count < 1 or 125 + property_count > len(packet):
        raise ValueError("invalid property value count")

    if packet[125] != 0:
        raise ValueError("unsupported sACN start code")

    if _pdu_length(packet, 16) != len(packet) - 16:
        raise ValueError("invalid root PDU length")

    if _pdu_length(packet, 38) != len(packet) - 38:
        raise ValueError("invalid framing PDU length")

    if _pdu_length(packet, 115) != len(packet) - 115:
        raise ValueError("invalid DMP PDU length")

    source_name = packet[44:108].split(b"\0", 1)[0].decode(
        "ascii",
        errors="replace",
    )

    return SacnDmxPacket(
        cid=packet[22:38],
        source_name=source_name,
        priority=packet[108],
        sequence=packet[111],
        options=packet[112],
        universe=_read16(packet, 113),
        start_code=packet[125],
        values=packet[126 : 126 + property_count - 1],
    )
