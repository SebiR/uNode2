from __future__ import annotations

import time
import socket

import pytest

from artnet_packets import (
    ARTNET_PORT,
    ARTNET_AC_FAIL_RECORD,
    make_artdmx,
    make_artaddress,
    make_artpollreply_for_subscriber,
    make_artsync,
    parse_artdmx,
)
from helpers import configured_port_address, send_artnet_packet, step, wait_for_status
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


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
) -> int:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1
    config["failsafeMode"] = failsafe_mode

    step(
        "Switching uNode to Art-Net -> DMX for hardware DMX test "
        f"(failsafe={failsafe_mode})"
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
        and int(data["failsafeMode"]) == failsafe_mode,
    )
    return universe


def _send_artdmx_repeated(
    unode_ip: str,
    universe: int,
    values: list[int],
    *,
    sequence: int,
    count: int = 4,
) -> None:
    packet = make_artdmx(
        universe,
        values,
        sequence=sequence,
    )

    for _index in range(count):
        send_artnet_packet(unode_ip, packet)
        time.sleep(0.05)


def _full_frame_pattern() -> list[int]:
    return [((index * 37) + 11) & 0xFF for index in range(512)]


def _wait_for_output_failsafe(unode_client: UNodeClient) -> dict:
    return wait_for_status(
        unode_client,
        lambda data: data["failsafeActive"] is True,
        timeout=7.0,
        interval=0.25,
    )


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

    scene = [5, 25, 50, 100, 150, 250]
    live = [210, 190, 170, 150, 130, 110]

    step(f"Sending scene ArtDmx before recording failsafe scene: {scene}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        scene,
        sequence=64,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        scene,
    )

    step("Recording current DMX output as persistent failsafe scene via ArtAddress")
    send_artnet_packet(
        unode_ip,
        make_artaddress(command=ARTNET_AC_FAIL_RECORD),
    )
    time.sleep(0.2)

    step(f"Sending different live ArtDmx before Failsafe-Scene timeout: {live}")
    _send_artdmx_repeated(
        unode_ip,
        universe,
        live,
        sequence=65,
    )
    _wait_for_rp2040_frame_values(
        rp2040_tool,
        live,
    )

    step("Waiting for uNode Art-Net output timeout / Failsafe Scene")
    status = _wait_for_output_failsafe(unode_client)
    step(f"uNode reports failsafe active: mode={status['failsafeModeName']}")

    frame = _wait_for_rp2040_frame_values(
        rp2040_tool,
        scene,
        timeout=3.0,
    )
    step(
        "RP2040 analyzer confirmed recorded failsafe scene output: "
        f"values={frame['values']}"
    )


def test_dmx_input_from_rp2040_reaches_artnet_receiver(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 1  # DMX -> Art-Net
    config["net"] = 0
    config["subnetId"] = 0
    config["universe"] = 1

    step("Switching uNode to DMX -> Art-Net for hardware DMX input test")
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
        step(f"Configuring RP2040 DMX sender with {len(values)} slots: {values}")
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
            "Python Art-Net receiver saw uNode ArtDmx: "
            f"universe={packet.universe}, length={packet.length}, "
            f"values={list(packet.values[:len(values)])}"
        )

        assert packet.length >= len(values)
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
