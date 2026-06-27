from __future__ import annotations

from artnet_packets import (
    ARTNET_AC_LED_LOCATE,
    ARTNET_AC_LED_NORMAL,
    make_artaddress,
)
from helpers import request_artpoll_reply, send_artnet_packet, step, wait_for_status
from unode_client import UNodeClient


def test_artaddress_sets_names_and_locate_state(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    del preserved_config  # Fixture restores names after the ArtAddress test.

    test_short_name = "TST_uNode"
    test_long_name = "uNode ArtAddress Integration Test"

    try:
        step(
            "Sending ArtAddress with temporary names and AcLedLocate command"
        )
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                short_name=test_short_name,
                long_name=test_long_name,
                command=ARTNET_AC_LED_LOCATE,
                bind_index=1,
            ),
        )

        step("Waiting until /api/status reports Locate active")
        status = wait_for_status(
            unode_client,
            lambda data: data.get("squawking") is True,
        )

        step(
            "Locate active: "
            f"squawking={status['squawking']}, name='{status['name']}'"
        )
        assert status["name"] == test_short_name

        step("Reading config after ArtAddress name programming")
        config = unode_client.get_config()
        assert config["shortName"] == test_short_name
        assert config["longName"] == test_long_name

        step("Checking ArtPollReply reflects ArtAddress names")
        reply = request_artpoll_reply(unode_ip)
        assert reply.short_name == test_short_name
        assert reply.long_name == test_long_name

        step("Sending ArtAddress AcLedNormal command")
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                command=ARTNET_AC_LED_NORMAL,
                bind_index=1,
            ),
        )

        step("Waiting until Locate is inactive again")
        status = wait_for_status(
            unode_client,
            lambda data: data.get("squawking") is False,
        )
        assert status["squawking"] is False
    finally:
        step("Ensuring Locate is off after ArtAddress test")
        send_artnet_packet(
            unode_ip,
            make_artaddress(
                command=ARTNET_AC_LED_NORMAL,
                bind_index=1,
            ),
        )
