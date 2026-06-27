from helpers import request_artpoll_reply, step
from unode_client import UNodeClient


def test_artpoll_reply_basic_fields(
    unode_client: UNodeClient,
    unode_ip: str,
) -> None:
    del unode_client  # Fixture enforces opt-in and authentication readiness.

    step("Sending ArtPoll and waiting for ArtPollReply")
    reply = request_artpoll_reply(unode_ip)

    step(
        "ArtPollReply received: "
        f"short='{reply.short_name}', long='{reply.long_name}', "
        f"net={reply.net}, subnet={reply.subnet}, swOut={reply.sw_out[0]}"
    )

    assert reply.port == 6454
    assert reply.short_name
    assert reply.long_name
    assert reply.node_report.startswith("#")
    assert reply.num_ports == 1
    assert reply.bind_index == 1
    assert reply.status2 & 0x08  # 15-bit Port-Address supported.
