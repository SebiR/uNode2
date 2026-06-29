from __future__ import annotations

import time
import socket

import pytest

from artnet_packets import (
    ARTNET_PORT,
    ARTNET_AC_CANCEL_MERGE,
    ARTNET_AC_FAIL_RECORD,
    make_artdmx,
    make_artaddress,
    make_artpollreply_for_subscriber,
    make_artsync,
    parse_artdmx,
)
from helpers import configured_port_address, send_artnet_packet, step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from sacn_packets import (
    SACN_PORT,
    make_sacn_dmx,
    parse_sacn_dmx,
    sacn_multicast_address,
)
from unode_client import UNodeClient

DMX_SPEC_BREAK_MIN_US = 92
DMX_SPEC_MAB_MIN_US = 12
DMX_NOMINAL_BAUD = 250_000
DMX_BAUD_TOLERANCE_PERCENT = 2.0
DMX_FULL_FRAME_SLOTS = 512
DMX_START_CODE_AND_SLOT_BITS = 11
DMX_FULL_FRAME_DATA_US = (
    (DMX_FULL_FRAME_SLOTS + 1)
    * DMX_START_CODE_AND_SLOT_BITS
    * 1_000_000
    / DMX_NOMINAL_BAUD
)
DMX_FULL_FRAME_MIN_PACKET_US = (
    DMX_SPEC_BREAK_MIN_US
    + DMX_SPEC_MAB_MIN_US
    + DMX_FULL_FRAME_DATA_US
)


def _wait_for_rp2040_frame_values(
    tool: Rp2040DmxTool,
    expected: list[int],
    *,
    start: int = 1,
    count: int | None = None,
    timeout: float = 4.0,
) -> dict:
    deadline = time.time() + timeout
    last_frame = {}
    read_count = len(expected) if count is None else count

    while time.time() < deadline:
        last_frame = tool.get_frame(start=start, count=read_count)
        if last_frame.get("values") == expected:
            return last_frame
        time.sleep(0.1)

    raise AssertionError(
        f"Timed out waiting for RP2040 DMX values at CH{start} "
        f"{expected}; last={last_frame}"
    )


def _configure_unode_output(
    unode_client: UNodeClient,
    preserved_config: dict,
    *,
    failsafe_mode: int = 0,
    merge_mode: int = 0,
    live_protocol: int = 0,
) -> int:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["liveProtocol"] = live_protocol
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1
    config["failsafeMode"] = failsafe_mode
    config["mergeMode"] = merge_mode

    step(
        "Switching uNode to network -> DMX for hardware DMX test "
        f"(liveProtocol={live_protocol}, failsafe={failsafe_mode}, "
        f"merge={merge_mode})"
    )

    reset_config = config.copy()
    reset_config["direction"] = 1  # DMX -> Art-Net, used to clear output runtime state.
    unode_client.save_config(reset_config)
    reset_universe = configured_port_address(reset_config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == reset_universe,
    )

    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 0
        and int(data["universe"]) == universe
        and int(data.get("liveProtocol", 0)) == live_protocol
        and int(data["failsafeMode"]) == failsafe_mode
        and int(data["mergeMode"]) == merge_mode,
    )
    return universe


def _send_artdmx_repeated(
    unode_ip: str,
    universe: int,
    values: list[int],
    *,
    sequence: int,
    physical: int = 0,
    count: int = 4,
) -> None:
    packet = make_artdmx(
        universe,
        values,
        sequence=sequence,
        physical=physical,
    )

    for _index in range(count):
        send_artnet_packet(unode_ip, packet)
        time.sleep(0.05)


def _send_sacn_repeated(
    unode_ip: str,
    universe: int,
    values: list[int],
    *,
    sequence: int,
    count: int = 4,
) -> None:
    for index in range(count):
        packet = make_sacn_dmx(
            universe=universe,
            values=values,
            sequence=((sequence + index - 1) % 255) + 1,
            source_name="uNode pytest sACN",
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(packet, (unode_ip, SACN_PORT))
        finally:
            sock.close()

        time.sleep(0.05)


def _full_frame_pattern() -> list[int]:
    return [((index * 37) + 11) & 0xFF for index in range(512)]


def _wait_for_merge_sources(
    unode_client: UNodeClient,
    expected_physicals: set[int],
) -> dict:
    return wait_for_status(
        unode_client,
        lambda data: {
            int(source["physical"])
            for source in data.get("artNetSources", [])
        }
        >= expected_physicals,
        timeout=3.0,
        interval=0.1,
    )


def _wait_until_merge_sources(
    unode_client: UNodeClient,
    expected_physicals: set[int],
    *,
    timeout: float = 7.0,
) -> dict:
    return wait_for_status(
        unode_client,
        lambda data: {
            int(source["physical"])
            for source in data.get("artNetSources", [])
        }
        == expected_physicals,
        timeout=timeout,
        interval=0.2,
    )


def _wait_for_output_failsafe(unode_client: UNodeClient) -> dict:
    return wait_for_status(
        unode_client,
        lambda data: data["failsafeActive"] is True,
        timeout=7.0,
        interval=0.25,
    )


def _percent_deviation(value: float, nominal: float) -> float:
    return ((value - nominal) / nominal) * 100.0


def _format_window(minimum: float | None, maximum: float | None, unit: str) -> str:
    if minimum is None and maximum is None:
        return f"not bounded by this test {unit}".strip()
    if maximum is None:
        return f">= {minimum:.0f} {unit}"
    if minimum is None:
        return f"<= {maximum:.0f} {unit}"
    return f"{minimum:.0f}..{maximum:.0f} {unit}"


def _report_timing_metric(
    name: str,
    stats: dict,
    *,
    unit: str,
    nominal: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    actual_min = float(stats["min"])
    actual_avg = float(stats["avg"])
    actual_max = float(stats["max"])
    deviation = (
        f", avg deviation={_percent_deviation(actual_avg, nominal):+.2f}%"
        if nominal is not None
        else ""
    )
    target = (
        f"nominal={nominal:.0f} {unit}, "
        if nominal is not None
        else ""
    )
    step(
        f"Timing {name}: actual min/avg/max="
        f"{actual_min:.1f}/{actual_avg:.1f}/{actual_max:.1f} {unit}; "
        f"{target}allowed {_format_window(minimum, maximum, unit)}"
        f"{deviation}"
    )


def _collect_full_frame_timing_stats(
    tool: Rp2040DmxTool,
    *,
    attempts: int = 3,
    duration: float = 2.0,
) -> dict:
    last_stats = {}

    for attempt in range(1, attempts + 1):
        step(
            "Collecting RP2040 timing statistics from live uNode DMX output "
            f"(attempt {attempt}/{attempts})"
        )
        tool.clear_stats()
        time.sleep(duration)
        last_stats = tool.get_stats()

        slots = last_stats["slots"]
        if (
            last_stats["frames"] >= 10
            and slots["min"] == DMX_FULL_FRAME_SLOTS
            and slots["max"] == DMX_FULL_FRAME_SLOTS
        ):
            return last_stats

        step(
            "Timing capture contained a non-512-slot frame; retrying to avoid "
            "a transient analyzer/USB-command edge case: "
            f"frames={last_stats['frames']}, short={last_stats['shortFrames']}, "
            f"lastSlots={last_stats['lastSlots']}, "
            f"slots min/max={slots['min']}/{slots['max']}"
        )

    return last_stats


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
    timeout: float = 5.0,
):
    deadline = time.time() + timeout
    last_packet = None

    while time.time() < deadline:
        remaining = max(0.05, deadline - time.time())
        sock.settimeout(remaining)
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
            return packet

    raise AssertionError(
        "Timed out waiting for ArtDmx from uNode "
        f"universe={universe}, expected={expected}, last={last_packet}"
    )


def _join_sacn_multicast(sock: socket.socket, *, local_ip: str, universe: int) -> None:
    group_ip = sacn_multicast_address(universe)
    membership = socket.inet_aton(group_ip) + socket.inet_aton(local_ip)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)


def _wait_for_sacn_from_unode(
    sock: socket.socket,
    *,
    unode_ip: str,
    universe: int,
    expected: list[int],
    timeout: float = 5.0,
):
    deadline = time.time() + timeout
    last_packet = None

    while time.time() < deadline:
        remaining = max(0.05, deadline - time.time())
        sock.settimeout(remaining)
        try:
            data, sender = sock.recvfrom(1024)
        except socket.timeout:
            break

        if sender[0] != unode_ip:
            continue

        try:
            packet = parse_sacn_dmx(data)
        except ValueError:
            continue

        last_packet = packet
        if packet.universe == universe and list(packet.values[: len(expected)]) == expected:
            return packet

    raise AssertionError(
        "Timed out waiting for sACN from uNode "
        f"universe={universe}, expected={expected}, last={last_packet}"
    )


def test_artnet_to_dmx_output_reaches_rp2040_analyzer(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    expected = [7, 23, 42, 99, 128, 201]
    step(f"Sending ArtDmx to uNode Port-Address {universe}: {expected}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        expected,
        sequence=31,
    )

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        expected,
    )
    step(
        "RP2040 analyzer saw expected DMX values: "
        f"slots={frame['slots']}, values={frame['values']}"
    )

    stats = rp2040_tool.get_stats()
    step(
        "RP2040 analyzer stats: "
        f"frames={stats['frames']}, fps={stats['fps']}, "
        f"lastBreakUs={stats['lastBreakUs']}, lastMabUs={stats['lastMabUs']}"
    )

    assert stats["frames"] > 0
    assert stats["lastSlots"] >= len(expected)


def test_sacn_to_dmx_output_reaches_rp2040_analyzer(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        live_protocol=1,
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    expected = [13, 37, 73, 101, 149, 211]
    step(f"Sending sACN to uNode Universe {universe}: {expected}")
    _send_sacn_repeated(
        unode_ip,
        universe,
        expected,
        sequence=41,
    )

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        expected,
    )
    step(
        "RP2040 analyzer saw expected sACN-driven DMX values: "
        f"slots={frame['slots']}, values={frame['values']}"
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(data.get("liveProtocol", -1)) == 1
        and data.get("sacnActive") is True
        and int(data.get("sacnPackets", 0)) > 0,
    )
    step(
        "uNode sACN status: "
        f"packets={status.get('sacnPackets')}, "
        f"fps={status.get('sacnFPS')}, "
        f"last={status.get('lastSacnPacketAge')} ms"
    )

    stats = rp2040_tool.get_stats()
    step(
        "RP2040 analyzer stats after sACN: "
        f"frames={stats['frames']}, fps={stats['fps']}, "
        f"lastBreakUs={stats['lastBreakUs']}, lastMabUs={stats['lastMabUs']}"
    )

    assert stats["frames"] > 0
    assert stats["lastSlots"] >= len(expected)


def test_artnet_to_dmx_htp_merge_uses_highest_values_from_two_physical_sources(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        merge_mode=0,  # HTP
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    source_a = [10, 200, 30, 220, 50, 240]
    source_b = [180, 20, 210, 40, 230, 60]
    expected = [max(a, b) for a, b in zip(source_a, source_b)]

    step(f"Sending HTP merge source Physical=0: {source_a}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a,
        sequence=71,
        physical=0,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_a,
    )

    step(f"Sending HTP merge source Physical=1: {source_b}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=71,
        physical=1,
    )

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        expected,
    )
    status = _wait_for_merge_sources(
        unode_client,
        {0, 1},
    )

    step(
        "RP2040 analyzer confirmed HTP merge output: "
        f"values={frame['values']}, sources={status['artNetSources']}"
    )


def test_artnet_to_dmx_ltp_merge_uses_latest_physical_source(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        merge_mode=1,  # LTP
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    source_a_first = [15, 25, 35, 45, 55, 65]
    source_b = [190, 180, 170, 160, 150, 140]
    source_a_latest = [70, 80, 90, 100, 110, 120]

    step(f"Sending first LTP merge source Physical=0: {source_a_first}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a_first,
        sequence=81,
        physical=0,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_a_first,
    )

    step(f"Sending second LTP merge source Physical=1: {source_b}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=81,
        physical=1,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_b,
    )

    step(f"Updating Physical=0 again; LTP output should follow latest source: {source_a_latest}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a_latest,
        sequence=82,
        physical=0,
    )

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_a_latest,
    )
    status = _wait_for_merge_sources(
        unode_client,
        {0, 1},
    )
    winning_physicals = {
        int(source["physical"])
        for source in status["artNetSources"]
        if source.get("winning", False)
    }

    step(
        "RP2040 analyzer confirmed LTP merge output: "
        f"values={frame['values']}, winning={winning_physicals}, "
        f"sources={status['artNetSources']}"
    )
    assert winning_physicals == {0}


def test_artnet_to_dmx_merge_source_timeout_falls_back_to_remaining_source(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        merge_mode=0,  # HTP
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    source_a = [200, 20, 200, 20, 200, 20]
    source_b = [10, 210, 10, 210, 10, 210]
    merged = [max(a, b) for a, b in zip(source_a, source_b)]

    step("Sending two HTP merge sources")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a,
        sequence=91,
        physical=0,
    )
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=91,
        physical=1,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        merged,
    )
    _wait_for_merge_sources(
        unode_client,
        {0, 1},
    )

    step("Refreshing only Physical=1 until Physical=0 expires from merge")
    deadline = time.time() + 5.5
    sequence = 92
    while time.time() < deadline:
        _send_artdmx_repeated(
            unode_ip,
            universe,
            source_b,
            sequence=sequence,
            physical=1,
            count=1,
        )
        sequence += 1
        time.sleep(0.2)

    status = _wait_until_merge_sources(
        unode_client,
        {1},
        timeout=6.0,
    )
    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_b,
    )

    step(
        "Merge source timeout fell back to remaining Physical=1 source: "
        f"values={frame['values']}, sources={status['artNetSources']}"
    )


def test_artnet_to_dmx_third_merge_source_is_rejected(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        merge_mode=1,  # LTP makes an accepted third source very obvious.
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    source_a = [11, 22, 33, 44, 55, 66]
    source_b = [101, 102, 103, 104, 105, 106]
    rejected_source_c = [240, 241, 242, 243, 244, 245]

    before = unode_client.get_json("/api/status")
    before_drops = before["artNetDiagnostics"]["mergeThirdSourceDrops"]

    step("Creating two active LTP merge sources")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a,
        sequence=101,
        physical=0,
    )
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=101,
        physical=1,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        source_b,
    )
    _wait_for_merge_sources(
        unode_client,
        {0, 1},
    )

    step("Sending a third Physical=2 merge source; it should be rejected")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        rejected_source_c,
        sequence=101,
        physical=2,
    )

    status = wait_for_status(
        unode_client,
        lambda data: data["artNetDiagnostics"]["mergeThirdSourceDrops"] > before_drops,
    )
    frame = rp2040_tool.get_frame(start=1, count=len(source_b))

    step(
        "Third merge source was rejected: "
        f"drops={status['artNetDiagnostics']['mergeThirdSourceDrops']}, "
        f"frame={frame['values']}, sources={status['artNetSources']}"
    )
    assert frame["values"] == source_b


def test_artaddress_cancel_merge_locks_output_to_next_source(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        merge_mode=0,  # HTP
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    source_a = [40, 220, 40, 220, 40, 220]
    source_b = [210, 30, 210, 30, 210, 30]
    locked_source_a = [80, 90, 100, 110, 120, 130]

    step("Creating two active HTP merge sources")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_a,
        sequence=111,
        physical=0,
    )
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=111,
        physical=1,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        [max(a, b) for a, b in zip(source_a, source_b)],
    )

    before = unode_client.get_json("/api/status")
    before_lock_drops = before["artNetDiagnostics"]["mergeLockDrops"]

    step("Sending ArtAddress AcCancelMerge")
    send_artnet_packet(
        unode_ip,
        make_artaddress(command=ARTNET_AC_CANCEL_MERGE),
    )

    step("Sending next ArtDmx from Physical=0; it should become the locked source")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        locked_source_a,
        sequence=112,
        physical=0,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        locked_source_a,
    )

    step("Sending Physical=1 after CancelMerge lock; it should be ignored")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        source_b,
        sequence=112,
        physical=1,
    )

    status = wait_for_status(
        unode_client,
        lambda data: data["artNetDiagnostics"]["mergeLockDrops"] > before_lock_drops,
    )
    frame = rp2040_tool.get_frame(start=1, count=len(locked_source_a))

    step(
        "CancelMerge lock rejected the other Physical source: "
        f"drops={status['artNetDiagnostics']['mergeLockDrops']}, "
        f"frame={frame['values']}, sources={status['artNetSources']}"
    )
    assert frame["values"] == locked_source_a


def test_artnet_to_dmx_output_maps_sparse_high_channels(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    values = [0] * 512
    values[0:6] = [1, 2, 3, 4, 5, 6]
    values[127:133] = [11, 22, 33, 44, 55, 66]
    values[506:512] = [101, 102, 103, 104, 105, 106]

    step("Sending full ArtDmx frame with low, middle, and high channel markers")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        values,
        sequence=41,
    )

    low = _wait_for_rp2040_frame_values(
        rp2040_tool,
        [1, 2, 3, 4, 5, 6],
        start=1,
    )
    middle = _wait_for_rp2040_frame_values(
        rp2040_tool,
        [11, 22, 33, 44, 55, 66],
        start=128,
    )
    high = _wait_for_rp2040_frame_values(
        rp2040_tool,
        [101, 102, 103, 104, 105, 106],
        start=507,
    )

    step(
        "RP2040 analyzer confirmed sparse channel mapping: "
        f"CH1={low['values']}, CH128={middle['values']}, CH507={high['values']}"
    )


def test_artnet_to_dmx_output_preserves_full_512_slot_frame(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    values = _full_frame_pattern()
    step("Sending full 512-slot ArtDmx frame and checking every DMX slot")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        values,
        sequence=45,
    )

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        values,
        count=512,
    )

    step(
        "RP2040 analyzer confirmed exact 512-slot DMX output: "
        f"slots={frame['slots']}, first={frame['values'][:4]}, "
        f"last={frame['values'][-4:]}"
    )
    assert frame["slots"] == 512


def test_artnet_to_dmx_output_timing_matches_dmx512_limits(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode for timing capture")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    values = _full_frame_pattern()
    step("Sending full 512-slot ArtDmx frame for DMX timing measurement")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        values,
        sequence=46,
    )

    _wait_for_rp2040_frame_values(
        rp2040_tool,
        values,
        count=512,
    )

    step("Clearing startup/transient analyzer stats before timing window")
    rp2040_tool.clear_stats()
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        values,
        count=512,
    )
    rp2040_tool.clear_stats()

    stats = _collect_full_frame_timing_stats(rp2040_tool)

    baud = float(stats["baudEstimate"])
    baud_tolerance = DMX_NOMINAL_BAUD * DMX_BAUD_TOLERANCE_PERCENT / 100.0
    baud_min = DMX_NOMINAL_BAUD - baud_tolerance
    baud_max = DMX_NOMINAL_BAUD + baud_tolerance

    _report_timing_metric(
        "Break",
        stats["breakUs"],
        unit="us",
        minimum=DMX_SPEC_BREAK_MIN_US,
    )
    _report_timing_metric(
        "Mark-After-Break",
        stats["mabUs"],
        unit="us",
        minimum=DMX_SPEC_MAB_MIN_US,
    )
    _report_timing_metric(
        "Data",
        stats["dataUs"],
        unit="us",
        nominal=DMX_FULL_FRAME_DATA_US,
    )
    _report_timing_metric(
        "Frame period",
        stats["frameUs"],
        unit="us",
        minimum=DMX_FULL_FRAME_MIN_PACKET_US,
    )
    _report_timing_metric(
        "Slots",
        stats["slots"],
        unit="slots",
        nominal=DMX_FULL_FRAME_SLOTS,
        minimum=DMX_FULL_FRAME_SLOTS,
        maximum=DMX_FULL_FRAME_SLOTS,
    )
    step(
        "Timing Baud: actual="
        f"{baud:.0f} Bd; nominal={DMX_NOMINAL_BAUD} Bd; "
        f"allowed {baud_min:.0f}..{baud_max:.0f} Bd "
        f"({DMX_BAUD_TOLERANCE_PERCENT:.1f}% test tolerance); "
        f"deviation={_percent_deviation(baud, DMX_NOMINAL_BAUD):+.2f}%"
    )

    assert stats["frames"] >= 10
    assert stats["breakUs"]["min"] >= DMX_SPEC_BREAK_MIN_US
    assert stats["mabUs"]["min"] >= DMX_SPEC_MAB_MIN_US
    assert stats["slots"]["min"] == DMX_FULL_FRAME_SLOTS
    assert stats["slots"]["max"] == DMX_FULL_FRAME_SLOTS
    assert stats["frameUs"]["min"] >= DMX_FULL_FRAME_MIN_PACKET_US
    assert baud_min <= baud <= baud_max


def test_artsync_flushes_pending_artdmx_to_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    baseline = [3, 3, 3, 3, 3, 3]
    pending = [70, 80, 90, 100, 110, 120]

    step(f"Sending baseline ArtDmx without ArtSync: {baseline}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        baseline,
        sequence=51,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        baseline,
    )

    step("Sending ArtSync to enable synchronous output mode")
    send_artnet_packet(unode_ip, make_artsync())
    wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is True
        and data["artSyncPending"] is False,
    )

    step(f"Sending pending ArtDmx under ArtSync: {pending}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        pending,
        sequence=52,
        count=1,
    )
    wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is True
        and data["artSyncPending"] is True,
    )

    observed = rp2040_tool.get_frame(start=1, count=len(pending))
    step(f"Before flush, RP2040 still sees: {observed['values']}")
    assert observed["values"] == baseline

    step("Sending ArtSync flush and waiting for real DMX output to change")
    send_artnet_packet(unode_ip, make_artsync())
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        pending,
    )


def test_artsync_timeout_flushes_pending_artdmx_to_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(unode_client, preserved_config)

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    baseline = [13, 13, 13, 13, 13, 13]
    pending = [91, 82, 73, 64, 55, 46]

    before_status = unode_client.get_json("/api/status")
    before_timeouts = int(before_status["artNetDiagnostics"]["syncTimeouts"])

    step(f"Sending baseline ArtDmx without ArtSync: {baseline}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        baseline,
        sequence=53,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        baseline,
    )

    step("Sending ArtSync to enable synchronous output mode")
    send_artnet_packet(unode_ip, make_artsync())
    wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is True
        and data["artSyncPending"] is False,
    )

    step(f"Sending pending ArtDmx under ArtSync without follow-up sync: {pending}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        pending,
        sequence=54,
        count=1,
    )
    wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is True
        and data["artSyncPending"] is True,
    )

    observed = rp2040_tool.get_frame(start=1, count=len(pending))
    step(f"Before timeout, RP2040 still sees: {observed['values']}")
    assert observed["values"] == baseline

    step("Waiting for ArtSync timeout and real DMX output flush")
    status = wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is False
        and data["artSyncPending"] is False
        and int(data["artNetDiagnostics"]["syncTimeouts"]) > before_timeouts,
        timeout=6.0,
        interval=0.2,
    )
    step(
        "ArtSync timeout reported: "
        f"syncTimeouts={status['artNetDiagnostics']['syncTimeouts']}"
    )

    _wait_for_rp2040_frame_values(
        rp2040_tool,
        pending,
        timeout=2.0,
    )
    step("RP2040 analyzer confirmed ArtSync timeout flushed pending DMX output")


def test_artnet_output_failsafe_zero_reaches_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        failsafe_mode=1,  # All to Zero
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    nonzero = [200, 180, 160, 140, 120, 100]
    zero = [0, 0, 0, 0, 0, 0]

    step(f"Sending non-zero ArtDmx before failsafe timeout: {nonzero}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        nonzero,
        sequence=61,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        nonzero,
    )

    step("Waiting for uNode Art-Net output timeout / All-to-Zero failsafe")
    status = wait_for_status(
        unode_client,
        lambda data: data["failsafeActive"] is True,
        timeout=7.0,
        interval=0.25,
    )
    step(f"uNode reports failsafe active: mode={status['failsafeModeName']}")

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        zero,
        timeout=3.0,
    )
    step(
        "RP2040 analyzer confirmed failsafe zero output: "
        f"values={frame['values']}"
    )


def test_artnet_output_failsafe_hold_keeps_last_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        failsafe_mode=0,  # Hold
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    held = [33, 66, 99, 132, 165, 198]
    step(f"Sending ArtDmx before Hold failsafe timeout: {held}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        held,
        sequence=62,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        held,
    )

    step("Waiting for uNode Art-Net output timeout / Hold failsafe")
    status = _wait_for_output_failsafe(unode_client)
    step(f"uNode reports failsafe active: mode={status['failsafeModeName']}")

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        held,
        timeout=3.0,
    )
    step(
        "RP2040 analyzer confirmed Hold keeps last DMX output: "
        f"values={frame['values']}"
    )


def test_artnet_output_failsafe_full_reaches_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        failsafe_mode=2,  # All to Full
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    nonfull = [10, 20, 30, 40, 50, 60]
    full = [255, 255, 255, 255, 255, 255]

    step(f"Sending non-full ArtDmx before All-to-Full timeout: {nonfull}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        nonfull,
        sequence=63,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        nonfull,
    )

    step("Waiting for uNode Art-Net output timeout / All-to-Full failsafe")
    status = _wait_for_output_failsafe(unode_client)
    step(f"uNode reports failsafe active: mode={status['failsafeModeName']}")

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        full,
        timeout=3.0,
    )
    step(
        "RP2040 analyzer confirmed failsafe full output: "
        f"values={frame['values']}"
    )


def test_artnet_output_failsafe_scene_reaches_real_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    universe = _configure_unode_output(
        unode_client,
        preserved_config,
        failsafe_mode=3,  # Failsafe Scene
    )

    step("Putting RP2040 DMX tool into RX analyzer mode")
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()

    scene = _full_frame_pattern()
    live = [255 - value for value in scene]

    step(
        "Sending full 512-slot scene ArtDmx before recording failsafe scene: "
        f"first={scene[:4]}, last={scene[-4:]}"
    )
    _send_artdmx_repeated(
        unode_ip,
        universe,
        scene,
        sequence=64,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        scene,
        count=512,
    )

    step("Recording current DMX output as persistent failsafe scene via ArtAddress")
    send_artnet_packet(
        unode_ip,
        make_artaddress(command=ARTNET_AC_FAIL_RECORD),
    )
    time.sleep(0.2)

    step(
        "Sending different full 512-slot live ArtDmx before Failsafe-Scene "
        f"timeout: first={live[:4]}, last={live[-4:]}"
    )
    _send_artdmx_repeated(
        unode_ip,
        universe,
        live,
        sequence=65,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        live,
        count=512,
    )

    step("Waiting for uNode Art-Net output timeout / Failsafe Scene")
    status = _wait_for_output_failsafe(unode_client)
    step(f"uNode reports failsafe active: mode={status['failsafeModeName']}")

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        scene,
        count=512,
        timeout=3.0,
    )
    step(
        "RP2040 analyzer confirmed recorded 512-slot failsafe scene output: "
        f"slots={frame['slots']}, first={frame['values'][:4]}, "
        f"last={frame['values'][-4:]}"
    )
    assert frame["slots"] == 512


def test_short_dmx_input_from_rp2040_reaches_artnet_receiver_without_full_padding(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> Art-Net
    config["liveProtocol"] = 0  # Art-Net output from DMX input
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to DMX -> Art-Net for short-frame DMX input test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == universe,
    )

    receiver_ip = _local_ipv4_for_target(unode_ip)
    subscriber_reply = make_artpollreply_for_subscriber(
        ip=receiver_ip,
        net=config["net"],
        subnet=config["subnetId"],
        universe=config["universe"],
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind(("", ARTNET_PORT))
        except OSError as error:
            pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

        step(
            "Advertising Python test receiver as Art-Net subscriber: "
            f"{receiver_ip}"
        )
        for _index in range(3):
            sock.sendto(subscriber_reply, (unode_ip, ARTNET_PORT))
            time.sleep(0.1)

        values = [9, 18, 27, 36, 45, 54]
        step(
            f"Configuring RP2040 DMX sender with a short {len(values)}-slot "
            f"frame: {values}"
        )
        rp2040_tool.mode("tx")
        rp2040_tool.set_timing(
            break_us=176,
            mab_us=16,
            fps=40,
        )
        rp2040_tool.set_frame(values, slots=len(values))

        step("Starting RP2040 DMX sender and waiting for uNode ArtDmx")
        rp2040_tool.tx("start")

        packet = _wait_for_artdmx_from_unode(
            sock,
            unode_ip=unode_ip,
            universe=universe,
            expected=values,
        )

        step(
            "Python Art-Net receiver saw short-frame uNode ArtDmx: "
            f"universe={packet.universe}, length={packet.length}, "
            f"values={list(packet.values[:len(values)])}"
        )

        assert len(values) <= packet.length < 512
        assert packet.length % 2 == 0
        assert list(packet.values[: len(values)]) == values
        assert set(packet.values[len(values) : packet.length]) <= {0}
    finally:
        rp2040_tool.idle()
        sock.close()


def test_dmx_input_from_rp2040_preserves_full_512_slot_artdmx(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> Art-Net
    config["liveProtocol"] = 0  # Art-Net output from DMX input
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to DMX -> Art-Net for full-frame input test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == universe,
    )

    receiver_ip = _local_ipv4_for_target(unode_ip)
    subscriber_reply = make_artpollreply_for_subscriber(
        ip=receiver_ip,
        net=config["net"],
        subnet=config["subnetId"],
        universe=config["universe"],
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind(("", ARTNET_PORT))
        except OSError as error:
            pytest.skip(f"UDP {ARTNET_PORT} is unavailable: {error}")

        step(
            "Advertising Python test receiver as Art-Net subscriber: "
            f"{receiver_ip}"
        )
        for _index in range(3):
            sock.sendto(subscriber_reply, (unode_ip, ARTNET_PORT))
            time.sleep(0.1)

        values = _full_frame_pattern()
        step("Configuring RP2040 DMX sender with a full 512-slot frame")
        rp2040_tool.mode("tx")
        rp2040_tool.set_timing(
            break_us=176,
            mab_us=16,
            fps=40,
        )
        rp2040_tool.set_frame(values, slots=512)

        step("Starting RP2040 DMX sender and waiting for full ArtDmx")
        rp2040_tool.tx("start")

        packet = _wait_for_artdmx_from_unode(
            sock,
            unode_ip=unode_ip,
            universe=universe,
            expected=values,
        )

        step(
            "Python Art-Net receiver confirmed exact 512-slot ArtDmx: "
            f"length={packet.length}, first={list(packet.values[:4])}, "
            f"last={list(packet.values[-4:])}"
        )

        assert packet.length == 512
        assert list(packet.values) == values
    finally:
        rp2040_tool.idle()
        sock.close()


def test_dmx_input_from_rp2040_is_sent_as_full_512_slot_sacn(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> network
    config["liveProtocol"] = 1  # sACN output from DMX input
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to DMX -> sACN for full-frame input test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == universe
        and int(data.get("liveProtocol", -1)) == 1,
    )

    receiver_ip = _local_ipv4_for_target(unode_ip)
    multicast_ip = sacn_multicast_address(universe)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        try:
            sock.bind(("", SACN_PORT))
            _join_sacn_multicast(sock, local_ip=receiver_ip, universe=universe)
        except OSError as error:
            pytest.skip(f"UDP {SACN_PORT} or multicast join is unavailable: {error}")

        values = _full_frame_pattern()
        step(
            "Configuring RP2040 DMX sender with a full 512-slot frame for "
            f"sACN multicast {multicast_ip}"
        )
        rp2040_tool.mode("tx")
        rp2040_tool.set_timing(
            break_us=176,
            mab_us=16,
            fps=40,
        )
        rp2040_tool.set_frame(values, slots=512)

        step("Starting RP2040 DMX sender and waiting for full sACN from uNode")
        rp2040_tool.tx("start")

        packet = _wait_for_sacn_from_unode(
            sock,
            unode_ip=unode_ip,
            universe=universe,
            expected=values,
        )

        step(
            "Python sACN receiver confirmed exact 512-slot DMX payload: "
            f"universe={packet.universe}, priority={packet.priority}, "
            f"sequence={packet.sequence}, source='{packet.source_name}', "
            f"first={list(packet.values[:4])}, last={list(packet.values[-4:])}"
        )

        assert packet.priority == 100
        assert len(packet.values) == 512
        assert list(packet.values) == values
    finally:
        rp2040_tool.idle()
        sock.close()
