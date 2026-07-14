"""Controlled Client-mode Wi-Fi loss and protocol-socket recovery checks.

This suite is opt-in because it deliberately makes the node unreachable for a
few seconds. The firmware keeps the stored Wi-Fi credentials untouched and
re-enters its normal exponential reconnect path after the requested outage.
"""

from __future__ import annotations

import os
import socket
import time
import uuid

import pytest

from helpers import (
    configured_port_address,
    local_ipv4_for_target,
    request_artpoll_reply,
    step,
    wait_for_status,
)
from sacn_packets import SACN_PORT, make_sacn_dmx, sacn_multicast_address
from unode_client import UNodeClient


pytestmark = pytest.mark.skipif(
    os.environ.get("UNODE_RUN_RECONNECTION") != "1",
    reason="Enable the controlled outage with UNODE_RUN_RECONNECTION=1",
)


def _send_sacn_multicast(unode_ip: str, universe: int, packet: bytes) -> None:
    """Send one sACN multicast packet through the interface reaching uNode."""

    local_ip = local_ipv4_for_target(unode_ip)
    destination = sacn_multicast_address(universe)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(local_ip),
        )
        sock.sendto(packet, (destination, SACN_PORT))
    finally:
        sock.close()


def test_client_reconnect_restores_http_artnet_and_sacn(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    request: pytest.FixtureRequest,
) -> None:
    initial_status = unode_client.get_json("/api/status")
    if not initial_status.get("wifiConnected", False):
        pytest.fail("Controlled reconnect requires Client or AP+Client mode")

    diagnostics = initial_status.get("networkDiagnostics", {})
    required_metrics = {
        "reconnectAttemptsTotal",
        "reconnectSuccesses",
        "lastReconnectDuration",
    }
    if not required_metrics.issubset(diagnostics):
        pytest.fail("Controlled reconnect requires firmware 0.23.26 or newer")

    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = 1
    config["busGuardMode"] = 0
    universe = configured_port_address(config)

    reset_config = config.copy()
    reset_config["liveProtocol"] = 0
    unode_client.save_config(reset_config)
    wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 0,
    )

    step(f"Preparing sACN multicast reception on Universe {universe}")
    saved = unode_client.save_config(config)
    assert saved.get("restartRequired") is False
    ready = wait_for_status(
        unode_client,
        lambda data: data.get("wifiConnected") is True
        and int(data.get("direction", -1)) == 0
        and int(data.get("liveProtocol", -1)) == 1
        and data.get("sacnDiagnostics", {}).get("multicastJoined") is True,
        timeout=5.0,
    )

    boot_count = int(ready["bootCount"])
    before_network = ready["networkDiagnostics"]
    before_attempts = int(before_network["reconnectAttemptsTotal"])
    before_successes = int(before_network["reconnectSuccesses"])
    before_rebinds = int(ready["sacnDiagnostics"]["socketRebinds"])
    before_sacn_packets = int(ready.get("sacnPackets", 0))
    outage_ms = int(os.environ.get("UNODE_RECONNECT_OUTAGE_MS", "3000"))
    outage_ms = min(15000, max(1000, outage_ms))

    step(
        "Scheduling controlled Client disconnect: "
        f"outage={outage_ms} ms, bootCount={boot_count}"
    )
    status_code, body = unode_client.post_json(
        "/api/network/reconnect",
        {"outageMs": outage_ms},
    )
    assert status_code == 202, body.decode(errors="replace")

    disconnect_observed = False
    observation_deadline = time.monotonic() + max(4.0, outage_ms / 1000.0 + 2.0)
    while time.monotonic() < observation_deadline:
        try:
            transient = unode_client.get_json("/api/status", timeout=0.25)
            if transient.get("wifiConnected") is False:
                disconnect_observed = True
                break
        except Exception:  # noqa: BLE001 - temporary transport loss is the expected event.
            disconnect_observed = True
            break
        time.sleep(0.05)

    assert disconnect_observed, "The requested Wi-Fi outage was not observable"
    step("Client link is down; waiting for normal reconnect/backoff logic")

    recovered = wait_for_status(
        unode_client,
        lambda data: data.get("wifiConnected") is True
        and int(data.get("networkDiagnostics", {}).get("reconnectSuccesses", 0))
        > before_successes,
        timeout=35.0,
        interval=0.2,
    )

    after_network = recovered["networkDiagnostics"]
    attempts_after = int(after_network["reconnectAttemptsTotal"])
    successes_after = int(after_network["reconnectSuccesses"])
    reconnect_duration = int(after_network["lastReconnectDuration"])
    rebinds_after = int(recovered["sacnDiagnostics"]["socketRebinds"])

    step(
        "Wi-Fi recovered without reboot: "
        f"attempts={attempts_after - before_attempts}, "
        f"duration={reconnect_duration} ms, socketRebinds={rebinds_after}"
    )
    assert int(recovered["bootCount"]) == boot_count
    assert attempts_after > before_attempts
    assert successes_after >= before_successes + 1
    assert reconnect_duration >= max(750, outage_ms - 500)
    assert rebinds_after > before_rebinds
    assert recovered["sacnDiagnostics"]["multicastJoined"] is True

    step("Checking ArtPollReply after the network interface recovered")
    reply = request_artpoll_reply(unode_ip, timeout=5.0)
    assert reply.ip == unode_ip

    step("Checking sACN multicast data after socket rebind")
    packet = make_sacn_dmx(
        universe=universe,
        sequence=1,
        values=[17, 34, 51, 68],
        source_name="uNode reconnect test",
        cid=uuid.uuid4().bytes,
    )
    for _ in range(3):
        _send_sacn_multicast(unode_ip, universe, packet)
        time.sleep(0.05)

    final_status = wait_for_status(
        unode_client,
        lambda data: int(data.get("sacnPackets", 0)) > before_sacn_packets,
        timeout=5.0,
    )
    assert int(final_status["bootCount"]) == boot_count

    request.node.user_properties.extend(
        [
            ("metric.outageRequestedMs", outage_ms),
            ("metric.reconnectDurationMs", reconnect_duration),
            ("metric.reconnectAttempts", attempts_after - before_attempts),
            ("metric.bootCountBefore", boot_count),
            ("metric.bootCountAfter", int(final_status["bootCount"])),
            ("metric.sacnSocketRebinds", rebinds_after - before_rebinds),
        ]
    )
