import pytest

from sacn_packets import make_sacn_dmx, parse_sacn_dmx, sacn_multicast_address


def test_sacn_multicast_address_for_universe():
    assert sacn_multicast_address(1) == "239.255.0.1"
    assert sacn_multicast_address(256) == "239.255.1.0"
    assert sacn_multicast_address(63999) == "239.255.249.255"


@pytest.mark.parametrize("universe", [0, 64000])
def test_sacn_multicast_address_rejects_invalid_universe(universe):
    with pytest.raises(ValueError):
        sacn_multicast_address(universe)


def test_sacn_dmx_wire_format_and_parser():
    packet = make_sacn_dmx(
        universe=513,
        values=[1, 2, 3, 255],
        sequence=7,
        priority=120,
        source_name="pytest source",
        options=0x40,
    )

    assert packet[0:2] == b"\x00\x10"
    assert packet[4:16] == b"ASC-E1.17\x00\x00\x00"
    assert packet[18:22] == b"\x00\x00\x00\x04"
    assert packet[40:44] == b"\x00\x00\x00\x02"
    assert packet[117] == 0x02
    assert packet[118] == 0xA1
    assert packet[113:115] == b"\x02\x01"
    assert packet[123:125] == b"\x00\x05"

    parsed = parse_sacn_dmx(packet)

    assert parsed.universe == 513
    assert parsed.values == bytes([1, 2, 3, 255])
    assert parsed.sequence == 7
    assert parsed.priority == 120
    assert parsed.options == 0x40
    assert parsed.source_name == "pytest source"


def test_sacn_dmx_rejects_oversized_payload():
    with pytest.raises(ValueError):
        make_sacn_dmx(values=bytes(513))


def test_sacn_parser_rejects_bad_identifier():
    packet = bytearray(make_sacn_dmx(values=[1]))
    packet[4] = 0

    with pytest.raises(ValueError):
        parse_sacn_dmx(bytes(packet))


def test_sacn_parser_rejects_non_zero_start_code():
    packet = bytearray(make_sacn_dmx(values=[1]))
    packet[125] = 0xDD

    with pytest.raises(ValueError):
        parse_sacn_dmx(bytes(packet))
