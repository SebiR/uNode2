from __future__ import annotations

import os
import random
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field

import pytest

from artnet_packets import (
    ARTNET_ID,
    ARTNET_PORT,
    ARTNET_PROTOCOL_VERSION,
    OP_DMX,
    make_artdmx,
    make_artpoll,
    make_artsync,
)
from helpers import configured_port_address, request_artpoll_reply, send_artnet_packet, step
from sacn_packets import SACN_PORT, make_sacn_dmx
from unode_client import UNodeClient


ARTNET_MAX_BUFFER = 530


@dataclass
class SoakStats:
    http_checks: int = 0
    poll_replies: int = 0
    artpoll_packets: int = 0
    artdmx_packets: int = 0
    sacn_packets: int = 0
    artsync_packets: int = 0
    parser_probes: int = 0
    config_changes: int = 0
    api_failures: int = 0
    poll_failures: int = 0
    transient_http_gaps: int = 0
    transient_poll_gaps: int = 0
    min_free_heap: int = 0
    max_heap_fragmentation: int = 0
    last_status: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HostSoakProfile:
    name: str
    live_protocol: int


@dataclass
class SoakStreamState:
    universe: int
    sacn_universe: int
    sent: int = 0
    error: BaseException | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _soak_duration_seconds() -> float:
    return max(5.0, float(os.environ.get("UNODE_SOAK_SECONDS", "60")))


def _soak_interval_seconds() -> float:
    return max(0.1, float(os.environ.get("UNODE_SOAK_INTERVAL", "1.0")))


def _reachability_grace_seconds() -> float:
    return max(1.0, float(os.environ.get("UNODE_SOAK_REACHABILITY_GRACE", "8.0")))


def _stream_fps() -> float:
    return min(44.0, max(1.0, float(os.environ.get("UNODE_SOAK_STREAM_FPS", "40"))))


def _post_failure_recovery_seconds() -> float:
    return max(
        0.0,
        float(os.environ.get("UNODE_SOAK_POST_FAILURE_RECOVERY", "420")),
    )


def _host_network_snapshot(unode_ip: str) -> str:
    """Capture compact host-side routing evidence without changing the link."""

    commands = [
        ["ip", "route", "get", unode_ip],
        ["ip", "neigh", "show", "to", unode_ip],
        ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"],
        ["ping", "-c", "1", "-W", "1", unode_ip],
    ]
    evidence: list[str] = []

    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=3.0,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            evidence.append(f"{' '.join(command)} => {type(error).__name__}")
            continue

        output = (result.stdout or result.stderr).strip().replace("\n", " | ")
        evidence.append(
            f"{' '.join(command)} => rc={result.returncode} {output[:600]}"
        )

    return " || ".join(evidence)


def _observe_post_failure_recovery(
    unode_client: UNodeClient,
    *,
    timeout: float,
) -> dict | None:
    """Wait after a failed soak so a delayed watchdog reset is recorded."""

    if timeout <= 0:
        return None

    deadline = time.monotonic() + timeout
    step(f"Watching for uNode recovery for up to {timeout:.0f}s")

    while time.monotonic() < deadline:
        try:
            status = unode_client.get_json("/api/status", timeout=1.0)
            step(
                "uNode recovered after soak failure: "
                f"bootCount={status.get('bootCount')} "
                f"uptime={status.get('uptime')} "
                f"resetReason={status.get('resetReason')!r} "
                f"resetInfo={status.get('resetInfo')!r}"
            )
            return status
        except Exception:  # noqa: BLE001 - recovery polling records final state.
            time.sleep(1.0)

    step("uNode did not recover during the post-failure observation window")
    return None


def _run_network_stream(
    unode_ip: str,
    profile: HostSoakProfile,
    state: SoakStreamState,
    fps: float,
) -> None:
    """Send realistic continuous live data independently of control checks."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence = 1
    next_packet = time.monotonic()
    lengths = (2, 4, 6, 24, 64, 128, 512)

    try:
        while not state.stop.is_set():
            now = time.monotonic()
            if now < next_packet:
                state.stop.wait(min(0.002, next_packet - now))
                continue

            with state.lock:
                universe = state.universe
                sacn_universe = state.sacn_universe
                sent = state.sent

            length = lengths[sent % len(lengths)]
            values = bytes((sent * 17 + index * 29) & 0xFF for index in range(length))

            if profile.live_protocol == 0:
                packet = make_artdmx(
                    universe,
                    values,
                    sequence=sequence,
                )
                target = (unode_ip, ARTNET_PORT)
            else:
                packet = make_sacn_dmx(
                    universe=sacn_universe,
                    values=values,
                    sequence=sequence,
                )
                target = (unode_ip, SACN_PORT)

            sock.sendto(packet, target)

            with state.lock:
                state.sent += 1

            sequence = (sequence + 1) & 0xFF
            if sequence == 0:
                sequence = 1

            next_packet += 1.0 / fps
            if next_packet < now - 0.1:
                next_packet = now
    except BaseException as error:  # noqa: BLE001 - propagated to the test thread.
        state.error = error
        state.stop.set()
    finally:
        sock.close()


def _opcode_bytes(opcode: int) -> bytes:
    return opcode.to_bytes(2, "little")


def _protocol_version_bytes(version: int = ARTNET_PROTOCOL_VERSION) -> bytes:
    return version.to_bytes(2, "big")


def _artdmx_header(
    *,
    universe: int = 0,
    length: int = 2,
    protocol_version: int = ARTNET_PROTOCOL_VERSION,
) -> bytes:
    return (
        ARTNET_ID
        + _opcode_bytes(OP_DMX)
        + _protocol_version_bytes(protocol_version)
        + b"\x00\x00"
        + (universe & 0x7FFF).to_bytes(2, "little")
        + int(length).to_bytes(2, "big")
    )


def _send_udp(unode_ip: str, packet: bytes) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, ARTNET_PORT))
    finally:
        sock.close()


def _send_sacn_udp(unode_ip: str, packet: bytes) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (unode_ip, SACN_PORT))
    finally:
        sock.close()


def _parser_probe_packets(universe: int) -> list[tuple[str, bytes]]:
    return [
        ("short packet", b"Art"),
        ("invalid Art-Net ID", b"Bad-Net\x00" + _opcode_bytes(OP_DMX)),
        (
            "unsupported protocol",
            _artdmx_header(universe=universe, protocol_version=1) + b"\x00\x00",
        ),
        (
            "malformed ArtDmx length",
            _artdmx_header(universe=universe, length=6) + b"\x01\x02",
        ),
        (
            "unsupported opcode",
            ARTNET_ID + _opcode_bytes(0x1234) + _protocol_version_bytes() + b"\x00\x00",
        ),
        ("oversized UDP packet", bytes(ARTNET_MAX_BUFFER + 1)),
    ]


def _runtime_soak_config(
    original: dict,
    rng: random.Random,
    iteration: int,
    profile: HostSoakProfile,
) -> dict:
    config = original.copy()
    config["liveProtocol"] = profile.live_protocol
    config["direction"] = 0
    config["mergeMode"] = rng.choice([0, 1])
    config["failsafeMode"] = rng.choice([0, 1, 2, 3])
    config["legacyArtPollReply"] = bool(iteration % 3 == 0)
    return config


def _read_status_with_timeout(unode_client: UNodeClient) -> dict:
    return unode_client.get_json("/api/status", timeout=2.0)


def _read_status_with_grace(
    unode_client: UNodeClient,
    *,
    grace: float,
) -> tuple[dict, int]:
    deadline = time.monotonic() + grace
    failures = 0
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            return _read_status_with_timeout(unode_client), failures
        except Exception as error:
            failures += 1
            last_error = error
            time.sleep(0.25)

    raise AssertionError(
        f"uNode HTTP API unreachable for {grace:.1f}s after {failures} attempts"
    ) from last_error


def _request_artpoll_reply_with_grace(
    unode_ip: str,
    *,
    grace: float,
):
    deadline = time.monotonic() + grace
    failures = 0
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            return request_artpoll_reply(unode_ip, timeout=1.0), failures
        except Exception as error:
            failures += 1
            last_error = error
            time.sleep(0.25)

    raise AssertionError(
        f"uNode ArtPollReply unreachable for {grace:.1f}s after {failures} attempts"
    ) from last_error


@pytest.mark.parametrize(
    "profile",
    [
        HostSoakProfile("artnet-output", 0),
        HostSoakProfile("sacn-output", 1),
    ],
    ids=lambda profile: profile.name,
)
def test_host_soak_network_output_and_runtime_stability(
    unode_client: UNodeClient,
    unode_ip: str,
    profile: HostSoakProfile,
) -> None:
    """Run host-driven network -> DMX stability tests against one uNode."""

    duration = _soak_duration_seconds()
    interval = _soak_interval_seconds()
    stream_fps = _stream_fps()
    grace = _reachability_grace_seconds()
    rng = random.Random(0xA27E7)
    original_config = unode_client.get_config()
    soak_config = original_config.copy()
    soak_config["direction"] = 0
    soak_config["liveProtocol"] = profile.live_protocol
    universe = configured_port_address(soak_config)
    sacn_universe = max(1, universe)
    deadline = time.monotonic() + duration
    stats = SoakStats()
    stream_state: SoakStreamState | None = None
    stream_thread: threading.Thread | None = None

    step(
        "Starting host-only network-output soak: "
        f"profile={profile.name} "
        f"duration={duration:.1f}s interval={interval:.2f}s "
        f"stream={stream_fps:.1f}fps "
        f"grace={grace:.1f}s artnetUniverse={universe} "
        f"sacnUniverse={sacn_universe}"
    )

    try:
        step(
            "Switching node to network -> DMX for host-only soak: "
            f"profile={profile.name}"
        )
        runtime_response = unode_client.apply_runtime_config(soak_config)
        assert runtime_response.get("persistent") is False

        initial_status = _read_status_with_timeout(unode_client)
        initial_boot_count = int(initial_status["bootCount"])
        initial_reset_reason = str(initial_status.get("resetReason", ""))
        stats.min_free_heap = int(initial_status.get("minimumFreeHeap", 0))
        stats.max_heap_fragmentation = int(initial_status.get("heapFragmentation", 0))
        stats.last_status = initial_status

        stream_state = SoakStreamState(
            universe=universe,
            sacn_universe=sacn_universe,
        )
        stream_thread = threading.Thread(
            target=_run_network_stream,
            args=(unode_ip, profile, stream_state, stream_fps),
            name=f"uNode-{profile.name}-stream",
            daemon=True,
        )
        stream_thread.start()

        iteration = 0
        while time.monotonic() < deadline:
            iteration += 1

            if stream_state.error is not None:
                raise AssertionError(
                    f"{profile.name} stream sender failed: {stream_state.error!r}"
                ) from stream_state.error

            try:
                status, failures = _read_status_with_grace(
                    unode_client,
                    grace=grace,
                )
                stats.http_checks += 1
                stats.last_status = status
                if failures:
                    stats.api_failures += failures
                    stats.transient_http_gaps += 1
                    step(
                        "HTTP reachability recovered: "
                        f"attemptFailures={failures}, uptime={status.get('uptime')}"
                    )
            except Exception as error:
                raise AssertionError(
                    "uNode HTTP API became unreachable during soak; "
                    f"recovered_attempt_failures={stats.api_failures}, "
                    f"last_status={stats.last_status}, cause={error}"
                ) from error

            boot_count = int(status["bootCount"])
            reset_reason = str(status.get("resetReason", ""))
            stats.min_free_heap = min(
                stats.min_free_heap,
                int(status.get("minimumFreeHeap", stats.min_free_heap)),
            )
            stats.max_heap_fragmentation = max(
                stats.max_heap_fragmentation,
                int(status.get("heapFragmentation", stats.max_heap_fragmentation)),
            )

            assert boot_count == initial_boot_count, (
                "uNode rebooted during soak: "
                f"initial_bootCount={initial_boot_count}, current_bootCount={boot_count}, "
                f"resetReason={reset_reason}, resetInfo={status.get('resetInfo', '')!r}"
            )
            assert reset_reason == initial_reset_reason, (
                "uNode reset reason changed during soak: "
                f"initial={initial_reset_reason!r}, current={reset_reason!r}, "
                f"resetInfo={status.get('resetInfo', '')!r}"
            )

            try:
                reply, failures = _request_artpoll_reply_with_grace(
                    unode_ip,
                    grace=grace,
                )
                stats.poll_replies += 1
                stats.artpoll_packets += 1
                if failures:
                    stats.poll_failures += failures
                    stats.transient_poll_gaps += 1
                    step(f"ArtPollReply reachability recovered: failures={failures}")
                assert reply.ip == status["ip"]
            except Exception as error:
                raise AssertionError(
                    "uNode ArtPollReply became unreachable during soak; "
                    f"recovered_attempt_failures={stats.poll_failures}, "
                    f"last_status={stats.last_status}, cause={error}"
                ) from error

            if iteration % 5 == 0:
                send_artnet_packet(unode_ip, make_artpoll())
                stats.artpoll_packets += 1

            if iteration % 7 == 0:
                send_artnet_packet(unode_ip, make_artsync())
                stats.artsync_packets += 1

            if iteration % 4 == 0:
                label, packet = rng.choice(_parser_probe_packets(universe))
                step(f"Soak parser probe: {label}")
                _send_udp(unode_ip, packet)
                stats.parser_probes += 1

                if profile.live_protocol == 1:
                    _send_sacn_udp(unode_ip, b"not-sacn")
                    stats.parser_probes += 1

            if iteration % 10 == 0:
                config = _runtime_soak_config(
                    original_config,
                    rng,
                    iteration,
                    profile,
                )
                step(
                    "Soak runtime config change: "
                    f"profile={profile.name} merge={config['mergeMode']} "
                    f"failsafe={config['failsafeMode']} "
                    f"legacy={config['legacyArtPollReply']}"
                )
                runtime_response = unode_client.apply_runtime_config(config)
                assert runtime_response.get("persistent") is False
                universe = configured_port_address(config)
                sacn_universe = max(1, universe)
                with stream_state.lock:
                    stream_state.universe = universe
                    stream_state.sacn_universe = sacn_universe
                stats.config_changes += 1

            time.sleep(interval)

    except Exception as error:
        if stream_state is not None:
            stream_state.stop.set()
        if stream_thread is not None:
            stream_thread.join(timeout=3.0)

        host_network = _host_network_snapshot(unode_ip)
        step(f"Host network snapshot after soak failure: {host_network}")
        recovered = _observe_post_failure_recovery(
            unode_client,
            timeout=_post_failure_recovery_seconds(),
        )
        recovery_summary = None
        if recovered is not None:
            recovery_summary = {
                key: recovered.get(key)
                for key in (
                    "bootCount",
                    "uptime",
                    "resetReason",
                    "resetInfo",
                    "freeHeap",
                    "maxFreeBlock",
                )
            }

        raise AssertionError(
            f"{error}; host_network={host_network}; "
            f"post_failure_status={recovery_summary}"
        ) from error
    finally:
        if stream_state is not None:
            stream_state.stop.set()
        if stream_thread is not None:
            stream_thread.join(timeout=3.0)
        if stream_state is not None:
            if profile.live_protocol == 0:
                stats.artdmx_packets = stream_state.sent
            else:
                stats.sacn_packets = stream_state.sent

        step("Restoring original runtime config after soak")
        try:
            unode_client.apply_runtime_config(original_config)
        except Exception as error:
            step(f"Could not restore original runtime config after soak: {error}")

    final_status = _read_status_with_timeout(unode_client)
    stats.last_status = final_status
    step(
        "Soak summary: "
        f"profile={profile.name}, "
        f"http={stats.http_checks}, artPolls={stats.artpoll_packets}, "
        f"pollReplies={stats.poll_replies}, "
        f"artdmx={stats.artdmx_packets}, sacn={stats.sacn_packets}, "
        f"artsync={stats.artsync_packets}, "
        f"parserProbes={stats.parser_probes}, configChanges={stats.config_changes}, "
        f"httpGaps={stats.transient_http_gaps}, pollGaps={stats.transient_poll_gaps}, "
        f"minFreeHeap={stats.min_free_heap}, "
        f"maxHeapFragmentation={stats.max_heap_fragmentation}%"
    )

    assert int(final_status["bootCount"]) == int(initial_status["bootCount"])
