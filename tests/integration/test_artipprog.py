from __future__ import annotations

import socket
import time

import pytest

from artnet_packets import (
    ARTNET_PORT,
    make_artipprog,
    parse_artipprogreply,
)
from helpers import step
from unode_client import UNodeClient


def _request_artipprog_reply(
    unode_ip: str,
    *,
    timeout: float = 2.0,
):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind(("", ARTNET_PORT))
        except OSError as error:
            pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

        sock.settimeout(timeout)
        sock.sendto(
            make_artipprog(
                command=0,
                port=ARTNET_PORT,
            ),
            (unode_ip, ARTNET_PORT),
        )

        deadline = time.time() + timeout
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                data, _sender = sock.recvfrom(1024)
            except socket.timeout as error:
                last_error = error
                break

            try:
                return parse_artipprogreply(data)
            except ValueError:
                continue

        raise AssertionError("No ArtIpProgReply received") from last_error
    finally:
        sock.close()


def test_artipprog_enquiry_reports_current_network_without_changing_it(
    unode_client: UNodeClient,
    unode_ip: str,
) -> None:
    step("Reading /api/status before ArtIpProg enquiry")
    before = unode_client.get_json("/api/status")

    step("Sending safe ArtIpProg enquiry")
    reply = _request_artipprog_reply(unode_ip)

    step(
        "ArtIpProgReply received: "
        f"ip={reply.ip}, subnet={reply.subnet}, gateway={reply.gateway}, "
        f"port={reply.port}, dhcp={reply.dhcp}"
    )

    assert reply.ip == before["ip"]
    assert reply.subnet == before["wifiSubnet"]
    assert reply.gateway == before["wifiGateway"]
    assert reply.port == ARTNET_PORT

    if before.get("wifiConnected") is False:
        assert reply.dhcp is False

    step("Checking node is still reachable after ArtIpProg enquiry")
    after = unode_client.get_json("/api/status")

    assert after["ip"] == before["ip"]
    assert after["wifiSubnet"] == before["wifiSubnet"]
    assert after["wifiGateway"] == before["wifiGateway"]
