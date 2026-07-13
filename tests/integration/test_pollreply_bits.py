from __future__ import annotations

from artnet_packets import ARTNET_AC_LED_LOCATE, ARTNET_AC_LED_NORMAL, make_artaddress
from helpers import (
    configured_port_address,
    request_artpoll_reply,
    send_artnet_packet,
    step,
    wait_for_status,
)
from unode_client import UNodeClient


PORT_TYPE_DMX_INPUT = 0x40
PORT_TYPE_DMX_OUTPUT = 0x80

GOOD_OUTPUT_MERGE_LTP = 0x02
GOOD_OUTPUT_STYLE_CONTINUOUS = 0xF0

STATUS1_INDICATOR_MASK = 0xC0
STATUS1_INDICATOR_LOCATE = 0x40
STATUS1_INDICATOR_NORMAL = 0xC0
STATUS1_PORT_ADDRESS_NETWORK_CONFIGURED = 0x20

STATUS2_WEB_CONFIG = 0x01
STATUS2_DHCP_CONFIGURED = 0x02
STATUS2_DHCP_CAPABLE = 0x04
STATUS2_15_BIT_PORT_ADDRESS = 0x08
STATUS2_SQUAWKING = 0x20

STATUS3_PORT_DIRECTION_CONFIGURABLE = 0x08
STATUS3_FAILSAFE_PROGRAMMABLE = 0x20
STATUS3_FAILSAFE_MASK = 0xC0


def _expected_status3(failsafe_mode: int) -> int:
    return (
        STATUS3_PORT_DIRECTION_CONFIGURABLE
        | STATUS3_FAILSAFE_PROGRAMMABLE
        | ((failsafe_mode & 0x03) << 6)
    )


def test_artpollreply_port_and_status_bits_follow_runtime_config(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    output_config = preserved_config.copy()
    output_config["direction"] = 0  # Art-Net -> DMX
    output_config["net"] = 2
    output_config["subnetId"] = 3
    output_config["universe"] = 4
    output_config["failsafeMode"] = 2  # All to Full
    output_config["mergeMode"] = 1  # LTP
    output_config["legacyArtPollReply"] = False

    step(
        "Applying temporary output config for PollReply bit checks: "
        "Net=2 Sub=3 Universe=4 Failsafe=Full Merge=LTP"
    )
    unode_client.save_config(output_config)
    output_port_address = configured_port_address(output_config)
    output_status = wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 0
        and int(data["universe"]) == output_port_address
        and int(data["failsafeMode"]) == output_config["failsafeMode"]
        and int(data["mergeMode"]) == output_config["mergeMode"],
    )

    step("Reading ArtPollReply in output mode")
    reply = request_artpoll_reply(unode_ip)

    step(
        "Output PollReply bits: "
        f"portType=0x{reply.port_types[0]:02X}, "
        f"goodOutA=0x{reply.good_output_a[0]:02X}, "
        f"goodOutB=0x{reply.good_output_b[0]:02X}, "
        f"status2=0x{reply.status2:02X}, status3=0x{reply.status3:02X}"
    )

    assert reply.net == output_config["net"]
    assert reply.subnet == output_config["subnetId"]
    assert reply.sw_out[0] == output_config["universe"]
    assert reply.sw_in[0] == 0
    assert reply.port_types[0] & PORT_TYPE_DMX_OUTPUT
    assert not (reply.port_types[0] & PORT_TYPE_DMX_INPUT)
    assert reply.good_output_a[0] & GOOD_OUTPUT_MERGE_LTP
    assert reply.good_output_b[0] == GOOD_OUTPUT_STYLE_CONTINUOUS
    assert reply.status1 & STATUS1_PORT_ADDRESS_NETWORK_CONFIGURED
    assert (reply.status1 & STATUS1_INDICATOR_MASK) == STATUS1_INDICATOR_NORMAL
    assert reply.status2 & STATUS2_WEB_CONFIG
    assert reply.status2 & STATUS2_DHCP_CAPABLE
    assert reply.status2 & STATUS2_15_BIT_PORT_ADDRESS
    assert not (reply.status2 & STATUS2_SQUAWKING)
    dhcp_client_active = bool(
        output_config.get("dhcp") is True
        and output_status.get("wifiConnected") is True
    )
    if dhcp_client_active:
        assert reply.status2 & STATUS2_DHCP_CONFIGURED
    else:
        assert not (reply.status2 & STATUS2_DHCP_CONFIGURED)
    assert (reply.status3 & STATUS3_FAILSAFE_MASK) == (
        output_config["failsafeMode"] << 6
    )
    assert (reply.status3 & ~STATUS3_FAILSAFE_MASK) == (
        _expected_status3(output_config["failsafeMode"]) & ~STATUS3_FAILSAFE_MASK
    )

    input_config = output_config.copy()
    input_config["direction"] = 1  # DMX -> Art-Net

    step("Switching temporary config to input mode for PollReply bit checks")
    unode_client.save_config(input_config)
    input_port_address = configured_port_address(input_config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == input_port_address,
    )

    step("Reading ArtPollReply in input mode")
    reply = request_artpoll_reply(unode_ip)

    step(
        "Input PollReply bits: "
        f"portType=0x{reply.port_types[0]:02X}, "
        f"swIn={reply.sw_in[0]}, swOut={reply.sw_out[0]}, "
        f"goodOutB=0x{reply.good_output_b[0]:02X}"
    )

    assert reply.net == input_config["net"]
    assert reply.subnet == input_config["subnetId"]
    assert reply.sw_in[0] == input_config["universe"]
    assert reply.sw_out[0] == 0
    assert reply.port_types[0] & PORT_TYPE_DMX_INPUT
    assert not (reply.port_types[0] & PORT_TYPE_DMX_OUTPUT)
    assert reply.good_output_b[0] == 0


def test_artpollreply_locate_bits_follow_artaddress(
    unode_client: UNodeClient,
    unode_ip: str,
) -> None:
    try:
        step("Sending ArtAddress Locate command for PollReply squawk bits")
        send_artnet_packet(
            unode_ip,
            make_artaddress(command=ARTNET_AC_LED_LOCATE),
        )
        wait_for_status(
            unode_client,
            lambda data: data.get("squawking") is True,
        )

        reply = request_artpoll_reply(unode_ip)
        step(
            "Locate PollReply bits: "
            f"status1=0x{reply.status1:02X}, status2=0x{reply.status2:02X}"
        )
        assert (reply.status1 & STATUS1_INDICATOR_MASK) == STATUS1_INDICATOR_LOCATE
        assert reply.status2 & STATUS2_SQUAWKING

        step("Sending ArtAddress Normal command for PollReply squawk bits")
        send_artnet_packet(
            unode_ip,
            make_artaddress(command=ARTNET_AC_LED_NORMAL),
        )
        wait_for_status(
            unode_client,
            lambda data: data.get("squawking") is False,
        )

        reply = request_artpoll_reply(unode_ip)
        step(
            "Normal PollReply bits: "
            f"status1=0x{reply.status1:02X}, status2=0x{reply.status2:02X}"
        )
        assert (reply.status1 & STATUS1_INDICATOR_MASK) == STATUS1_INDICATOR_NORMAL
        assert not (reply.status2 & STATUS2_SQUAWKING)
    finally:
        step("Ensuring Locate is off after PollReply bit test")
        send_artnet_packet(
            unode_ip,
            make_artaddress(command=ARTNET_AC_LED_NORMAL),
        )
