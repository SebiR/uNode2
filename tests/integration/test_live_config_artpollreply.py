from __future__ import annotations

from helpers import configured_port_address, request_artpoll_reply, step, wait_for_status
from unode_client import UNodeClient


def _next_value(value: int, modulo: int) -> int:
    return (int(value) + 1) % modulo


def test_live_config_update_is_reflected_in_status_and_artpollreply(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    original = preserved_config.copy()
    modified = original.copy()

    modified["direction"] = 0  # Art-Net -> DMX, therefore SwOut[0] is active.
    modified["net"] = _next_value(original.get("net", 0), 128)
    modified["subnetId"] = _next_value(original.get("subnetId", 0), 16)
    modified["universe"] = _next_value(original.get("universe", 0), 16)
    modified_port_address = configured_port_address(modified)

    step(
        "Applying temporary live config: "
        f"direction={modified['direction']}, "
        f"net={modified['net']}, subnet={modified['subnetId']}, "
        f"universe={modified['universe']}"
    )
    response = unode_client.save_config(modified)
    assert response.get("appliedLive") is True
    assert response.get("restartRequired") is False

    step(
        "Waiting until /api/status reports the temporary Port-Address "
        f"{modified_port_address}"
    )
    status = wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == modified["direction"]
        and int(data["universe"]) == modified_port_address,
    )

    step(
        "Status reflects live config: "
        f"direction={status['direction']}, portAddress={status['universe']}"
    )

    step("Reading config back via REST API")
    saved_config = unode_client.get_config()
    assert int(saved_config["direction"]) == modified["direction"]
    assert int(saved_config["net"]) == modified["net"]
    assert int(saved_config["subnetId"]) == modified["subnetId"]
    assert int(saved_config["universe"]) == modified["universe"]

    step("Sending ArtPoll and checking ArtPollReply Port-Address fields")
    reply = request_artpoll_reply(unode_ip)

    step(
        "ArtPollReply reflects live config: "
        f"net={reply.net}, subnet={reply.subnet}, swOut[0]={reply.sw_out[0]}"
    )

    assert reply.net == modified["net"]
    assert reply.subnet == modified["subnetId"]
    assert reply.sw_out[0] == modified["universe"]
    assert reply.short_name == modified["shortName"]
    assert reply.long_name == modified["longName"]
