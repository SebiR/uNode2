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
    last_error: Exception | None = None

    while time.time() < deadline:
        remaining = deadline - time.time()
        request_timeout = max(0.2, min(1.0, remaining))
        try:
            last_status = client.get_json(
                "/api/status",
                timeout=request_timeout,
            )
            last_error = None
            if predicate(last_status):
                return last_status
        except Exception as error:  # noqa: BLE001 - status polling tolerates transient Wi-Fi/API hiccups.
            last_error = error

        time.sleep(interval)

    detail = f"last={last_status}"
    if last_error is not None:
        detail += f"; last_error={last_error!r}"

    raise AssertionError(f"Timed out waiting for status condition; {detail}")


def wait_for_node_restart(
    client,
    *,
    previous_boot_count: int,
    timeout: float = 25.0,
    interval: float = 0.5,
) -> dict:
    """Poll `/api/status` until the node is reachable after a reboot."""

    deadline = time.time() + timeout
    last_error: Exception | None = None
    last_status: dict = {}

    while time.time() < deadline:
        try:
            last_status = client.get_json("/api/status", timeout=2.0)
            if int(last_status.get("bootCount", previous_boot_count)) > previous_boot_count:
                return last_status
        except Exception as error:  # noqa: BLE001 - reboot polling intentionally tolerates transport errors.
            last_error = error

        time.sleep(interval)

    raise AssertionError(
        "Timed out waiting for node restart; "
        f"last_status={last_status}, last_error={last_error}"
    )


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
    """Poll repeatedly and return the first valid ArtPollReply.

    The HTTP server may become reachable slightly before the Art-Net UDP
    listener after a node restart. Re-sending ArtPoll also makes the helper
    tolerant of one lost Wi-Fi/UDP packet without hiding a sustained failure.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind((local_ipv4_for_target(unode_ip), ARTNET_PORT))
        except OSError as error:
            pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

        packet = make_artpoll()
        deadline = time.monotonic() + timeout
        next_poll = 0.0
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_poll:
                sock.sendto(packet, (unode_ip, ARTNET_PORT))
                next_poll = now + 0.25

            remaining = deadline - time.monotonic()
            sock.settimeout(max(0.01, min(0.1, remaining)))
            try:
                data, sender = sock.recvfrom(1024)
            except socket.timeout as error:
                last_error = error
                continue

            if sender[0] != unode_ip:
                continue

            try:
                return parse_artpollreply(data)
            except ValueError:
                continue

        raise AssertionError("No ArtPollReply received") from last_error
    finally:
        sock.close()
