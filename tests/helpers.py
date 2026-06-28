"""Shared helpers for uNode integration tests."""

from __future__ import annotations

import socket
import time
from typing import Callable

import pytest

from artnet_packets import ARTNET_PORT, ArtPollReply, make_artpoll, parse_artpollreply
from unode_client import UNodeClient


def step(message: str) -> None:
    """Print a human-readable integration-test progress message."""

    print(f"[uNode] {message}", flush=True)


def configured_port_address(config: dict) -> int:
    """Return the 15-bit Art-Net Port-Address from a uNode config object."""

    return (
        int(config["net"]) * 256
        + int(config["subnetId"]) * 16
        + int(config["universe"])
    )


def wait_for_status(
    client: UNodeClient,
    predicate: Callable[[dict], bool],
    *,
    timeout: float = 3.0,
    interval: float = 0.1,
) -> dict:
    """Poll `/api/status` until `predicate` accepts the returned data."""

    deadline = time.time() + timeout
    last_status = {}

    while time.time() < deadline:
        last_status = client.get_json("/api/status")
        if predicate(last_status):
            return last_status
        time.sleep(interval)

    raise AssertionError(f"Timed out waiting for status condition; last={last_status}")


def send_artnet_packet(unode_ip: str, packet: bytes) -> None:
    """Send one Art-Net UDP packet to the target node."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, ARTNET_PORT))
    finally:
        sock.close()


def local_ipv4_for_target(target_ip: str) -> str:
    """Return the local IPv4 address used to reach `target_ip`."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, ARTNET_PORT))
        return sock.getsockname()[0]
    finally:
        sock.close()


def request_artpoll_reply(
    unode_ip: str,
    *,
    timeout: float = 2.0,
) -> ArtPollReply:
    """Send ArtPoll to the target node and return the first valid ArtPollReply."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind((local_ipv4_for_target(unode_ip), ARTNET_PORT))
        except OSError as error:
            pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

        sock.settimeout(timeout)
        sock.sendto(make_artpoll(), (unode_ip, ARTNET_PORT))

        deadline = time.time() + timeout
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                data, sender = sock.recvfrom(1024)
            except socket.timeout as error:
                last_error = error
                break

            if sender[0] != unode_ip:
                continue

            try:
                return parse_artpollreply(data)
            except ValueError:
                continue

        raise AssertionError("No ArtPollReply received") from last_error
    finally:
        sock.close()
