from __future__ import annotations

import os
import time

import pytest

from helpers import step
from rp2040_dmx_tool import Rp2040DmxTool
from test_latency_hil import (
    ARTNET,
    SACN,
    LiveProtocol,
    _configure_input,
    _configure_output,
    _drain_udp,
    _open_artnet_receiver,
    _open_sacn_receiver,
    _pattern,
    _send_network_frame,
    _wait_for_network_values,
)
from unode_client import UNodeClient


def _dropout_samples() -> int:
    return max(1, int(os.environ.get("UNODE_DROPOUT_SAMPLES", "100")))


def _dropout_timeout_seconds() -> float:
    return max(0.25, float(os.environ.get("UNODE_DROPOUT_TIMEOUT", "1.5")))


def _dropout_interval_seconds() -> float:
    return max(0.0, float(os.environ.get("UNODE_DROPOUT_INTERVAL", "0.05")))


def _allowed_losses() -> int:
    return max(0, int(os.environ.get("UNODE_DROPOUT_ALLOWED_LOSSES", "0")))


def _print_delivery_report(
    *,
    title: str,
    sent: int,
    seen: int,
    lost_indices: list[int],
    duration_s: float,
) -> None:
    lost = sent - seen
    rate = sent / duration_s if duration_s > 0 else 0.0
    step("")
    step(f"Dropout report: {title}")
    step(f"Updates      : {sent} sent, {seen} seen, {lost} lost")
    step(f"Rate         : {rate:.1f} updates/s over {duration_s:.2f}s")
    if lost_indices:
        preview = ", ".join(str(index) for index in lost_indices[:12])
        suffix = "..." if len(lost_indices) > 12 else ""
        step(f"Lost indices : {preview}{suffix}")


@pytest.mark.parametrize("protocol", [ARTNET, SACN], ids=lambda p: p.name)
def test_each_network_update_reaches_physical_dmx_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
    protocol: LiveProtocol,
) -> None:
    samples = _dropout_samples()
    timeout = _dropout_timeout_seconds()
    interval = _dropout_interval_seconds()
    universe = _configure_output(unode_client, preserved_config, protocol)

    step(
        f"Starting {protocol.name} -> DMX dropout check: "
        f"{samples} unique updates, interval={interval:.3f}s, "
        f"timeout={timeout:.3f}s"
    )
    rp2040_tool.mode("rx")
    rp2040_tool.clear_stats()
    time.sleep(0.2)

    timeout_ms = round(timeout * 1000)
    seen = 0
    lost_indices: list[int] = []
    started = time.perf_counter()

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
            seen += 1
        else:
            lost_indices.append(sample_index + 1)
            step(
                f"{protocol.name} -> DMX update {sample_index + 1} was not "
                f"seen after {wait_result.get('framesSeen')} DMX frames"
            )

        if interval > 0:
            time.sleep(interval)

    duration_s = time.perf_counter() - started
    _print_delivery_report(
        title=f"{protocol.name} -> DMX",
        sent=samples,
        seen=seen,
        lost_indices=lost_indices,
        duration_s=duration_s,
    )

    assert len(lost_indices) <= _allowed_losses()


@pytest.mark.parametrize("protocol", [ARTNET, SACN], ids=lambda p: p.name)
def test_each_physical_dmx_change_reaches_network_output(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
    rp2040_tool: Rp2040DmxTool,
    protocol: LiveProtocol,
) -> None:
    samples = _dropout_samples()
    timeout = _dropout_timeout_seconds()
    interval = _dropout_interval_seconds()
    universe = _configure_input(unode_client, preserved_config, protocol)

    if protocol.value == ARTNET.value:
        sock = _open_artnet_receiver(unode_ip, universe)
    else:
        sock = _open_sacn_receiver(unode_ip, universe)

    try:
        step(
            f"Starting DMX -> {protocol.name} dropout check: "
            f"{samples} unique DMX changes, interval={interval:.3f}s, "
            f"timeout={timeout:.3f}s"
        )
        rp2040_tool.mode("tx")
        rp2040_tool.set_timing(break_us=176, mab_us=16, fps=40)

        seen = 0
        lost_indices: list[int] = []
        started = time.perf_counter()

        for sample_index in range(samples):
            values = _pattern(sample_index)
            rp2040_tool.set_frame(values, slots=len(values))
            _drain_udp(sock)

            rp2040_tool.tx("send")
            if _wait_for_network_values(
                sock,
                unode_ip=unode_ip,
                protocol=protocol,
                universe=universe,
                expected=values,
                timeout=timeout,
            ):
                seen += 1
            else:
                lost_indices.append(sample_index + 1)
                step(
                    f"DMX -> {protocol.name} update {sample_index + 1} "
                    "did not produce a matching network packet"
                )

            if interval > 0:
                time.sleep(interval)

        duration_s = time.perf_counter() - started
        _print_delivery_report(
            title=f"DMX -> {protocol.name}",
            sent=samples,
            seen=seen,
            lost_indices=lost_indices,
            duration_s=duration_s,
        )

        assert len(lost_indices) <= _allowed_losses()
    finally:
        rp2040_tool.idle()
        sock.close()
