from __future__ import annotations

import os
import socket
import statistics
import time
from dataclasses import dataclass

import pytest

from artnet_packets import (
    ARTNET_PORT,
    make_artdmx,
    make_artpollreply_for_subscriber,
    parse_artdmx,
)
from helpers import configured_port_address, local_ipv4_for_target, send_artnet_packet, step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from sacn_packets import SACN_PORT, make_sacn_dmx, parse_sacn_dmx, sacn_multicast_address
from unode_client import UNodeClient


@dataclass(frozen=True)
class LiveProtocol:
    name: str
    value: int


ARTNET = LiveProtocol("Art-Net", 0)
SACN = LiveProtocol("sACN", 1)


def _latency_samples() -> int:
    return max(3, int(os.environ.get("UNODE_LATENCY_SAMPLES", "12")))


def _latency_timeout_seconds() -> float:
    return max(0.25, float(os.environ.get("UNODE_LATENCY_TIMEOUT", "1.5")))


def _artnet_subscriber_refresh_seconds() -> float:
    return max(
        0.25,
        float(os.environ.get("UNODE_ARTNET_SUBSCRIBER_REFRESH", "1.0")),
    )


def _pattern(sample: int, *, length: int = 16) -> list[int]:
    base = ((sample + 1) * 17) & 0xFF
    return [((base + index * 29) & 0xFF) for index in range(length)]


def _summarize_ms(samples: list[float]) -> dict[str, float]:
    sorted_samples = sorted(samples)
    p95_index = min(
        len(sorted_samples) - 1,
        max(0, round((len(sorted_samples) - 1) * 0.95)),
    )
    return {
        "min": sorted_samples[0],
        "median": statistics.median(sorted_samples),
        "avg": statistics.mean(sorted_samples),
        "p95": sorted_samples[p95_index],
        "max": sorted_samples[-1],
    }


def _print_latency_report(
    *,
    title: str,
    status: dict,
    samples: list[float],
    lost: int,
) -> None:
    summary = _summarize_ms(samples)
    if status.get("wifiConnected") is True and status.get("softAPActive") is True:
        network_mode = "AP + Client"
    elif status.get("wifiConnected") is True:
        network_mode = "Client"
    elif status.get("softAPActive") is True:
        network_mode = "AP"
    else:
        network_mode = "unknown"
    ip = status.get("ip", "unknown")

    step("")
    step(f"Latency report: {title}")
    step(f"Network mode : {network_mode}")
    step(f"Node IP      : {ip}")
    step(f"Samples      : {len(samples)} ok, {lost} lost")
    step(
        "Latency     : "
        f"min {summary['min']:.1f} ms | "
        f"median {summary['median']:.1f} ms | "
        f"avg {summary['avg']:.1f} ms | "
        f"p95 {summary['p95']:.1f} ms | "
        f"max {summary['max']:.1f} ms"
    )


def _configure_output(
    unode_client: UNodeClient,
    preserved_config: dict,
    protocol: LiveProtocol,
) -> int:
    config = preserved_config.copy()
    config["direction"] = 0  # network -> DMX
    config["liveProtocol"] = protocol.value
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1
    config["failsafeMode"] = 0
    config["mergeMode"] = 0
    config["artSyncEnabled"] = False

    step(f"Switching uNode to {protocol.name} -> DMX latency profile")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 0
        and int(data["universe"]) == universe
        and int(data.get("liveProtocol", -1)) == protocol.value,
    )
    return universe


def _configure_input(
    unode_client: UNodeClient,
    preserved_config: dict,
    protocol: LiveProtocol,
) -> int:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> network
    config["liveProtocol"] = protocol.value
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1
    config["sacnSourceName"] = "uNode latency test"
    config["sacnPriority"] = 100

    step(f"Switching uNode to DMX -> {protocol.name} latency profile")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == universe
        and int(data.get("liveProtocol", -1)) == protocol.value,
    )
    return universe


def _send_network_frame(
    *,
    unode_ip: str,
    protocol: LiveProtocol,
    universe: int,
    values: list[int],
    sequence: int,
) -> None:
    if protocol.value == ARTNET.value:
        send_artnet_packet(
            unode_ip,
            make_artdmx(universe, values, sequence=sequence, physical=0),
        )
        return

    packet = make_sacn_dmx(
        universe=universe,
        values=values,
        sequence=sequence,
        source_name="uNode latency sender",
        priority=100,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, SACN_PORT))
    finally:
        sock.close()


def _open_artnet_receiver(unode_ip: str, universe: int) -> socket.socket:
    receiver_ip = local_ipv4_for_target(unode_ip)
    subscriber_reply = make_artpollreply_for_subscriber(
        ip=receiver_ip,
        net=0,
        subnet=0,
        universe=universe,
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", ARTNET_PORT))
    except OSError as error:
        sock.close()
        pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

    step(f"Advertising Python latency receiver as Art-Net subscriber: {receiver_ip}")
    for _index in range(3):
        sock.sendto(subscriber_reply, (unode_ip, ARTNET_PORT))
        time.sleep(0.1)
    return sock


def make_artnet_subscriber_reply(unode_ip: str, universe: int) -> bytes:
    return make_artpollreply_for_subscriber(
        ip=local_ipv4_for_target(unode_ip),
        net=0,
        subnet=0,
        universe=universe,
    )


def refresh_artnet_subscriber(
    sock: socket.socket,
    *,
    unode_ip: str,
    subscriber_reply: bytes,
) -> None:
    sock.sendto(subscriber_reply, (unode_ip, ARTNET_PORT))


def _open_sacn_receiver(unode_ip: str, universe: int) -> socket.socket:
    receiver_ip = local_ipv4_for_target(unode_ip)
    group_ip = sacn_multicast_address(universe)
    membership = socket.inet_aton(group_ip) + socket.inet_aton(receiver_ip)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", SACN_PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    except OSError as error:
        sock.close()
        pytest.skip(f"UDP {SACN_PORT} or multicast join is unavailable: {error}")

    step(f"Listening for uNode sACN multicast on {group_ip} via {receiver_ip}")
    return sock


def _drain_udp(sock: socket.socket) -> None:
    sock.setblocking(False)
    try:
        while True:
            try:
                sock.recvfrom(2048)
            except BlockingIOError:
                return
    finally:
        sock.setblocking(True)


def _wait_for_network_values(
    sock: socket.socket,
    *,
    unode_ip: str,
    protocol: LiveProtocol,
    universe: int,
    expected: list[int],
    timeout: float,
) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        sock.settimeout(max(0.01, deadline - time.perf_counter()))
        try:
            data, sender = sock.recvfrom(2048)
        except socket.timeout:
            return False

        if sender[0] != unode_ip:
            continue

        try:
            if protocol.value == ARTNET.value:
                packet = parse_artdmx(data)
                if (
                    packet.universe == universe
                    and list(packet.values[: len(expected)]) == expected
                ):
                    return True
            else:
                packet = parse_sacn_dmx(data)
                if (
                    packet.universe == universe
                    and list(packet.values[: len(expected)]) == expected
                ):
                    return True
        except ValueError:
            continue

    return False


@pytest.mark.parametrize("protocol", [ARTNET, SACN], ids=lambda p: p.name)
def test_network_to_dmx_latency_profile(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
    protocol: LiveProtocol,
) -> None:
    samples = _latency_samples()
    timeout = _latency_timeout_seconds()
    universe = _configure_output(unode_client, preserved_config, protocol)
    status = unode_client.get_json("/api/status")

    step("Putting RP2040 into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()
    time.sleep(0.2)
    timeout_ms = round(timeout * 1000)

    latencies: list[float] = []
    lost = 0
    for sample_index in range(samples):
        values = _pattern(sample_index)
        sequence = ((sample_index + 1) % 255) or 1
        rp2040_tool.begin_wait_frame(values, timeout_ms=timeout_ms)
        _send_network_frame(
            unode_ip=unode_ip,
            protocol=protocol,
            universe=universe,
            values=values,
            sequence=sequence,
        )
        wait_result = rp2040_tool.finish_wait_frame(timeout_ms=timeout_ms)

        if wait_result.get("matched") is True:
            latencies.append(float(wait_result["elapsedUs"]) / 1000.0)
        else:
            lost += 1
            step(
                f"{protocol.name} -> DMX latency sample {sample_index + 1} "
                f"timed out after seeing {wait_result.get('framesSeen')} frames"
            )

        time.sleep(0.05)

    _print_latency_report(
        title=f"{protocol.name} -> DMX",
        status=status,
        samples=latencies,
        lost=lost,
    )

    assert latencies, f"No {protocol.name} -> DMX latency samples succeeded"
    assert lost <= max(1, samples // 4)


@pytest.mark.parametrize("protocol", [ARTNET, SACN], ids=lambda p: p.name)
def test_dmx_to_network_latency_profile(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
    protocol: LiveProtocol,
) -> None:
    samples = _latency_samples()
    timeout = _latency_timeout_seconds()
    universe = _configure_input(unode_client, preserved_config, protocol)
    status = unode_client.get_json("/api/status")

    if protocol.value == ARTNET.value:
        sock = _open_artnet_receiver(unode_ip, universe)
        artnet_subscriber_reply = make_artnet_subscriber_reply(unode_ip, universe)
        next_artnet_refresh = time.perf_counter() + _artnet_subscriber_refresh_seconds()
    else:
        sock = _open_sacn_receiver(unode_ip, universe)
        artnet_subscriber_reply = b""
        next_artnet_refresh = 0.0

    try:
        step(
            "Putting RP2040 into single-frame TX mode. "
            "DMX -> network latency includes the USB trigger command, so use "
            "this as a practical AP/client comparison rather than a pure "
            "microcontroller-only timing number."
        )
        rp2040_tool.mode("tx")
        rp2040_tool.set_timing(break_us=176, mab_us=16, fps=40)

        latencies: list[float] = []
        lost = 0
        for sample_index in range(samples):
            values = _pattern(sample_index)
            rp2040_tool.set_frame(values, slots=len(values))
            _drain_udp(sock)

            if protocol.value == ARTNET.value and time.perf_counter() >= next_artnet_refresh:
                refresh_artnet_subscriber(
                    sock,
                    unode_ip=unode_ip,
                    subscriber_reply=artnet_subscriber_reply,
                )
                next_artnet_refresh = (
                    time.perf_counter() + _artnet_subscriber_refresh_seconds()
                )

            start = time.perf_counter()
            rp2040_tool.tx("send")
            if _wait_for_network_values(
                sock,
                unode_ip=unode_ip,
                protocol=protocol,
                universe=universe,
                expected=values,
                timeout=timeout,
            ):
                latencies.append((time.perf_counter() - start) * 1000.0)
            else:
                lost += 1
                step(f"DMX -> {protocol.name} latency sample {sample_index + 1} timed out")

            time.sleep(0.05)

        _print_latency_report(
            title=f"DMX -> {protocol.name}",
            status=status,
            samples=latencies,
            lost=lost,
        )

        assert latencies, f"No DMX -> {protocol.name} latency samples succeeded"
        assert lost <= max(1, samples // 4)
    finally:
        rp2040_tool.idle()
        sock.close()
