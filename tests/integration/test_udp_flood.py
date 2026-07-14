"""Stress oversized and high-rate foreign UDP traffic on both live-data ports."""

from __future__ import annotations

import errno
import os
import socket
import threading
import time
from dataclasses import dataclass, field

import pytest

from artnet_packets import ARTNET_PORT, make_artdmx
from helpers import configured_port_address, request_artpoll_reply, step, wait_for_status
from sacn_packets import SACN_PORT, make_sacn_dmx
from unode_client import UNodeClient


MAX_IPV4_UDP_PAYLOAD = 65_507


@dataclass(frozen=True)
class FloodProfile:
    name: str
    live_protocol: int
    port: int
    parser_limit: int


@dataclass
class FloodState:
    attempted: int = 0
    sent: int = 0
    host_backpressure_drops: int = 0
    error: BaseException | None = None
    stop: threading.Event = field(default_factory=threading.Event)


PROFILES = (
    FloodProfile("Art-Net", 0, ARTNET_PORT, 530),
    FloodProfile("sACN", 1, SACN_PORT, 638),
)


def _flood_seconds() -> float:
    return max(2.0, float(os.environ.get("UNODE_UDP_FLOOD_SECONDS", "8")))


def _flood_pps() -> float:
    # Keep the regression default above realistic live-data rates without
    # turning it into a Wi-Fi PHY/driver denial-of-service test. On ESP8266,
    # sufficiently intense fragmented radio traffic can trip the closed SDK's
    # wDev interrupt watchdog before lwIP or application code sees a packet.
    return min(5000.0, max(10.0, float(os.environ.get("UNODE_UDP_FLOOD_PPS", "250"))))


def _payload(size: int, seed: int) -> bytes:
    """Create deterministic non-protocol data without random allocation churn."""

    pattern = bytes(((seed * 41 + index * 73) & 0xFF) for index in range(256))
    repeats, remainder = divmod(size, len(pattern))
    return pattern * repeats + pattern[:remainder]


def _run_flood(
    unode_ip: str,
    profile: FloodProfile,
    state: FloodState,
    *,
    duration: float,
    pps: float,
) -> None:
    """Send a paced mix of small and fragmented foreign UDP datagrams."""

    sizes = (
        32,
        64,
        128,
        512,
        profile.parser_limit + 1,
        1024,
        4096,
        8192,
    )
    payloads = tuple(_payload(size, index + 1) for index, size in enumerate(sizes))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
    sock.setblocking(False)
    deadline = time.monotonic() + duration
    next_packet = time.monotonic()

    try:
        while time.monotonic() < deadline and not state.stop.is_set():
            now = time.monotonic()
            if now < next_packet:
                state.stop.wait(min(0.001, next_packet - now))
                continue

            payload = payloads[state.attempted % len(payloads)]
            state.attempted += 1
            try:
                sock.sendto(payload, (unode_ip, profile.port))
                state.sent += 1
            except OSError as error:
                if error.errno not in {
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                    errno.ENOBUFS,
                }:
                    raise
                state.host_backpressure_drops += 1
            next_packet += 1.0 / pps

            if next_packet < now - 0.1:
                next_packet = now
    except BaseException as error:  # noqa: BLE001 - forwarded to the test thread.
        state.error = error
    finally:
        sock.close()


def _send_jumbo_probes(unode_ip: str, profile: FloodProfile) -> list[int]:
    """Send selected sizes through the host IP fragmentation path."""

    sent_sizes: list[int] = []
    sizes = (
        profile.parser_limit + 1,
        2048,
        8192,
        32_768,
        MAX_IPV4_UDP_PAYLOAD,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        for index, size in enumerate(sizes):
            try:
                written = sock.sendto(
                    _payload(size, 20 + index),
                    (unode_ip, profile.port),
                )
            except OSError as error:
                step(f"Host could not send {size}-byte UDP probe: {error}")
                continue

            assert written == size
            sent_sizes.append(size)
            time.sleep(0.05)
    finally:
        sock.close()

    return sent_sizes


def _send_valid_live_packet(
    unode_ip: str,
    profile: FloodProfile,
    universe: int,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if profile.live_protocol == 0:
            packet = make_artdmx(
                universe,
                [17, 34, 51, 68],
                sequence=1,
            )
        else:
            packet = make_sacn_dmx(
                universe=max(1, universe),
                values=[17, 34, 51, 68],
                sequence=1,
            )
        sock.sendto(packet, (unode_ip, profile.port))
    finally:
        sock.close()


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile.name)
def test_foreign_udp_flood_is_bounded_and_recovers(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    record_property,
    profile: FloodProfile,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0
    config["liveProtocol"] = profile.live_protocol
    unode_client.save_config(config)

    universe = configured_port_address(config)
    initial = wait_for_status(
        unode_client,
        lambda status: int(status.get("liveProtocol", -1))
        == profile.live_protocol,
    )
    initial_boot_count = int(initial["bootCount"])
    initial_fragment_count = int(
        initial["networkDiagnostics"]["ipv4FragmentsDropped"]
    )
    if profile.live_protocol == 0:
        initial_parser_count = int(
            initial["artNetDiagnostics"]["oversizedPackets"]
        )
        initial_live_count = int(initial["artnetPackets"])
    else:
        initial_parser_count = int(
            initial["sacnDiagnostics"]["malformedPackets"]
        )
        initial_live_count = int(initial["sacnPackets"])

    step(f"Sending jumbo foreign UDP probes to {profile.name} port {profile.port}")
    jumbo_sizes = _send_jumbo_probes(unode_ip, profile)
    assert profile.parser_limit + 1 in jumbo_sizes

    duration = _flood_seconds()
    pps = _flood_pps()
    state = FloodState()
    thread = threading.Thread(
        target=_run_flood,
        args=(unode_ip, profile, state),
        kwargs={"duration": duration, "pps": pps},
        name=f"uNode-{profile.name}-foreign-udp-flood",
        daemon=True,
    )
    step(
        f"Flooding {profile.name} with foreign UDP for {duration:.1f}s "
        f"at up to {pps:.0f} packets/s"
    )
    thread.start()

    http_checks = 0
    transient_http_failures = 0
    while thread.is_alive():
        try:
            status = unode_client.get_json("/api/status", timeout=0.75)
            http_checks += 1
            assert int(status["bootCount"]) == initial_boot_count
        except AssertionError:
            state.stop.set()
            raise
        except Exception:  # noqa: BLE001 - saturation may delay the control plane.
            transient_http_failures += 1
        time.sleep(0.2)

    thread.join(timeout=2.0)
    assert state.error is None, repr(state.error)
    assert state.attempted >= int(duration * pps * 0.75)
    assert state.sent >= 100

    step(
        f"Flood ended: attempted={state.attempted}, sent={state.sent}, "
        f"host backpressure={state.host_backpressure_drops}, "
        f"HTTP checks={http_checks}, "
        f"transient HTTP failures={transient_http_failures}"
    )
    recovered = wait_for_status(
        unode_client,
        lambda status: int(status.get("bootCount", -1)) == initial_boot_count,
        timeout=15.0,
        interval=0.2,
    )

    assert recovered["heapWarningActive"] is False
    assert int(recovered["freeHeap"]) >= int(recovered["heapWarningFreeThreshold"])
    assert int(recovered["maxFreeBlock"]) >= int(
        recovered["heapWarningBlockThreshold"]
    )
    assert recovered["networkDiagnostics"]["ipFragmentGuardEnabled"] is True
    assert int(
        recovered["networkDiagnostics"]["ipv4FragmentsDropped"]
    ) > initial_fragment_count

    if profile.live_protocol == 0:
        parser_count = int(recovered["artNetDiagnostics"]["oversizedPackets"])
    else:
        parser_count = int(recovered["sacnDiagnostics"]["malformedPackets"])
    assert parser_count > initial_parser_count

    step(f"Sending valid {profile.name} data after the foreign-packet flood")
    _send_valid_live_packet(unode_ip, profile, universe)
    final = wait_for_status(
        unode_client,
        lambda status: int(
            status["artnetPackets"]
            if profile.live_protocol == 0
            else status["sacnPackets"]
        )
        > initial_live_count,
        timeout=10.0,
        interval=0.1,
    )
    request_artpoll_reply(unode_ip, timeout=5.0)

    record_property(
        "metric.udpFlood",
        {
            "protocol": profile.name,
            "durationSeconds": duration,
            "targetPacketsPerSecond": pps,
            "packetsAttempted": state.attempted,
            "packetsSent": state.sent,
            "hostBackpressureDrops": state.host_backpressure_drops,
            "jumboSizes": jumbo_sizes,
            "httpChecks": http_checks,
            "transientHttpFailures": transient_http_failures,
            "freeHeapAfter": int(final["freeHeap"]),
            "largestFreeBlockAfter": int(final["maxFreeBlock"]),
            "bootCount": initial_boot_count,
        },
    )
