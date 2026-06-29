from __future__ import annotations

import os
import random
import socket
import time
from dataclasses import dataclass

from artnet_packets import (
    ARTNET_PORT,
    make_artpollreply_for_subscriber,
    parse_artdmx,
)
from helpers import configured_port_address, step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


@dataclass(frozen=True)
class DmxInputScenario:
    name: str
    slots: int
    break_us: int
    mab_us: int
    baud: int = 250000
    fps: int = 40
    inter_slot_us: int = 0
    mbb_us: int = 0
    expect_forwarded_artdmx: bool = True
    noise: bool = False


def _dmx_soak_duration_seconds() -> float:
    return max(10.0, float(os.environ.get("UNODE_DMX_SOAK_SECONDS", "60")))


def _local_ipv4_for_target(target_ip: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, ARTNET_PORT))
        return sock.getsockname()[0]
    finally:
        sock.close()


def _wait_for_artdmx_from_unode(
    sock: socket.socket,
    *,
    unode_ip: str,
    universe: int,
    expected: list[int],
    timeout: float = 4.0,
) -> None:
    deadline = time.time() + timeout
    last_packet = None

    while time.time() < deadline:
        sock.settimeout(max(0.05, deadline - time.time()))
        try:
            data, sender = sock.recvfrom(1024)
        except socket.timeout:
            break

        if sender[0] != unode_ip:
            continue

        try:
            packet = parse_artdmx(data)
        except ValueError:
            continue

        last_packet = packet
        if packet.universe == universe and list(packet.values[: len(expected)]) == expected:
            return

    raise AssertionError(
        "Timed out waiting for ArtDmx from uNode during DMX soak "
        f"universe={universe}, expected={expected[:8]}, last={last_packet}"
    )


def _drain_udp(sock: socket.socket) -> None:
    sock.settimeout(0.01)
    while True:
        try:
            sock.recvfrom(1024)
        except socket.timeout:
            return


def _scenario_values(index: int, slots: int) -> list[int]:
    return [((index * 29) + (slot * 17) + 3) & 0xFF for slot in range(slots)]


def _configure_unode_input(unode_client: UNodeClient, preserved_config: dict) -> tuple[dict, int]:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> Art-Net
    config["liveProtocol"] = 0  # Art-Net output from DMX input
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to DMX -> Art-Net for DMX HIL soak")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == universe,
    )
    return config, universe


def _rp2040_supports_noise(tool: Rp2040DmxTool) -> bool:
    try:
        help_response = tool.help()
    except AssertionError:
        return False

    commands = [
        str(command)
        for command in help_response.get("commands", [])
    ]
    return any('"cmd":"noise"' in command for command in commands)


def _advertise_subscriber(
    sock: socket.socket,
    *,
    unode_ip: str,
    config: dict,
    receiver_ip: str,
) -> None:
    subscriber_reply = make_artpollreply_for_subscriber(
        ip=receiver_ip,
        net=config["net"],
        subnet=config["subnetId"],
        universe=config["universe"],
    )
    for _index in range(3):
        sock.sendto(subscriber_reply, (unode_ip, ARTNET_PORT))
        time.sleep(0.05)


def test_dmx_input_hil_soak_survives_timing_faults(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config, universe = _configure_unode_input(unode_client, preserved_config)
    duration = _dmx_soak_duration_seconds()
    deadline = time.time() + duration
    receiver_ip = _local_ipv4_for_target(unode_ip)

    scenarios = [
        DmxInputScenario("valid-short-6ch", 6, 176, 16),
        DmxInputScenario("valid-minimum-timing", 24, 92, 12),
        DmxInputScenario("valid-long-inter-slot-gap", 6, 176, 16, inter_slot_us=100),
        DmxInputScenario("valid-full-frame", 512, 176, 16, fps=30),
        DmxInputScenario(
            "invalid-short-break",
            6,
            44,
            12,
            expect_forwarded_artdmx=False,
        ),
        DmxInputScenario(
            "invalid-zero-mab",
            6,
            176,
            0,
            expect_forwarded_artdmx=False,
        ),
        DmxInputScenario(
            "edge-fast-baud",
            12,
            176,
            16,
            baud=300000,
            expect_forwarded_artdmx=False,
        ),
        DmxInputScenario(
            "edge-slow-baud",
            12,
            176,
            16,
            baud=200000,
            expect_forwarded_artdmx=False,
        ),
        DmxInputScenario(
            "random-line-noise",
            0,
            176,
            16,
            expect_forwarded_artdmx=False,
            noise=True,
        ),
    ]
    rng = random.Random(0xD111_50A5)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    iterations = 0
    forwarded_checks = 0
    fault_injections = 0

    try:
        sock.bind(("", ARTNET_PORT))
        _advertise_subscriber(
            sock,
            unode_ip=unode_ip,
            config=config,
            receiver_ip=receiver_ip,
        )

        initial_status = unode_client.get_json("/api/status")
        initial_boot_count = int(initial_status["bootCount"])
        initial_reset_reason = str(initial_status.get("resetReason", ""))
        noise_supported = _rp2040_supports_noise(rp2040_tool)
        if not noise_supported:
            step("RP2040 firmware does not support noise command; skipping line-noise bursts")

        rp2040_tool.mode("tx")

        step(
            "Starting DMX HIL soak: "
            f"duration={duration:.1f}s receiver={receiver_ip} universe={universe}"
        )

        while time.time() < deadline:
            if iterations % 5 == 4:
                scenario = DmxInputScenario(
                    "random-uart-garbage",
                    rng.randint(0, 512),
                    rng.randint(44, 5000),
                    rng.randint(0, 2000),
                    baud=rng.randint(200000, 300000),
                    fps=rng.randint(5, 80),
                    inter_slot_us=rng.randint(0, 500),
                    mbb_us=rng.randint(0, 5000),
                    expect_forwarded_artdmx=False,
                )
            else:
                scenario = scenarios[iterations % len(scenarios)]
            iterations += 1
            values = _scenario_values(iterations, scenario.slots)

            step(
                "DMX soak scenario "
                f"{iterations}: {scenario.name} slots={scenario.slots} "
                f"break={scenario.break_us}us mab={scenario.mab_us}us "
                f"baud={scenario.baud} inter={scenario.inter_slot_us}us"
            )

            _drain_udp(sock)
            _advertise_subscriber(
                sock,
                unode_ip=unode_ip,
                config=config,
                receiver_ip=receiver_ip,
            )
            if scenario.noise:
                if noise_supported:
                    rp2040_tool.noise(
                        duration_ms=rng.randint(50, 250),
                        min_pulse_us=rng.randint(1, 10),
                        max_pulse_us=rng.randint(20, 500),
                    )
                else:
                    time.sleep(0.1)
            else:
                rp2040_tool.mode("tx")
                rp2040_tool.set_timing(
                    break_us=scenario.break_us,
                    mab_us=scenario.mab_us,
                    fps=scenario.fps,
                    inter_slot_us=scenario.inter_slot_us,
                    mbb_us=scenario.mbb_us,
                    baud=scenario.baud,
                )
                rp2040_tool.set_frame(values, slots=scenario.slots)
                rp2040_tool.tx("start")

            if scenario.expect_forwarded_artdmx:
                _wait_for_artdmx_from_unode(
                    sock,
                    unode_ip=unode_ip,
                    universe=universe,
                    expected=values,
                    timeout=4.0,
                )
                forwarded_checks += 1
            else:
                fault_injections += 1
                time.sleep(0.75)

                recovery_values = _scenario_values(iterations + 1000, 6)
                _drain_udp(sock)
                _advertise_subscriber(
                    sock,
                    unode_ip=unode_ip,
                    config=config,
                    receiver_ip=receiver_ip,
                )
                rp2040_tool.set_timing(
                    break_us=176,
                    mab_us=16,
                    fps=40,
                    baud=250000,
                )
                rp2040_tool.set_frame(recovery_values, slots=6)
                rp2040_tool.tx("start")
                _wait_for_artdmx_from_unode(
                    sock,
                    unode_ip=unode_ip,
                    universe=universe,
                    expected=recovery_values,
                    timeout=4.0,
                )
                forwarded_checks += 1

            status = unode_client.get_json("/api/status", timeout=2.0)
            assert int(status["bootCount"]) == initial_boot_count, (
                "uNode rebooted during DMX HIL soak: "
                f"initial={initial_boot_count}, current={status['bootCount']}, "
                f"resetReason={status.get('resetReason')}, "
                f"resetInfo={status.get('resetInfo', '')!r}"
            )
            assert str(status.get("resetReason", "")) == initial_reset_reason

        final_stats = rp2040_tool.get_stats()
        step(
            "DMX HIL soak summary: "
            f"iterations={iterations}, forwardedChecks={forwarded_checks}, "
            f"faultInjections={fault_injections}, "
            f"rp2040Mode={final_stats.get('mode')}"
        )

    finally:
        rp2040_tool.idle()
        sock.close()
