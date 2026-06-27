from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from serial.tools import list_ports

from helpers import step
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient

_TEST_REPORTS: dict[str, dict[str, object]] = {}


def integration_enabled() -> bool:
    return os.environ.get("UNODE_RUN_INTEGRATION") == "1"


def _read_node_status() -> dict:
    base_url = os.environ.get("UNODE_BASE_URL", "http://2.0.0.1").rstrip("/")
    request = urllib.request.Request(base_url + "/api/status", method="GET")

    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.HTTPError, json.JSONDecodeError):
        return {}


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call":
        if report.passed:
            status = "PASSED"
        elif report.failed:
            status = "FAILED"
        else:
            status = "SKIPPED"
    elif report.when == "setup" and report.skipped:
        status = "SKIPPED"
    else:
        return

    _TEST_REPORTS[report.nodeid] = {
        "status": status,
        "duration": report.duration,
    }


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    del exitstatus, config

    now = datetime.now().astimezone()
    terminalreporter.write_sep("=", "uNode Test Certificate")

    if integration_enabled():
        status = _read_node_status()
        chip_id = status.get("chipId", "unknown")
        firmware = status.get("firmware", "unknown")
        node_name = status.get("name", "unknown")
        ip = status.get("ip", os.environ.get("UNODE_IP", "unknown"))
        terminalreporter.write_line(
            f"Node       : {node_name} {chip_id} (FW {firmware})"
        )
        terminalreporter.write_line(f"IP         : {ip}")
        rp2040 = os.environ.get("UNODE_RP2040_PORT")
        if rp2040:
            terminalreporter.write_line(f"RP2040     : {rp2040}")
    else:
        terminalreporter.write_line("Node       : offline/unit test run")

    terminalreporter.write_line(f"Test Date  : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    terminalreporter.write_line(f"UTC        : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    terminalreporter.write_line("")

    counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0}
    for nodeid in sorted(_TEST_REPORTS):
        result = _TEST_REPORTS[nodeid]
        status_text = str(result["status"])
        counts[status_text] = counts.get(status_text, 0) + 1
        duration = float(result["duration"])
        terminalreporter.write_line(
            f"[{status_text:<7}] {nodeid} ({duration:.2f}s)"
        )

    terminalreporter.write_line("")
    terminalreporter.write_line(
        "Summary    : "
        f"{counts.get('PASSED', 0)} passed, "
        f"{counts.get('FAILED', 0)} failed, "
        f"{counts.get('SKIPPED', 0)} skipped"
    )


@pytest.fixture(scope="session")
def unode_ip() -> str:
    return os.environ.get("UNODE_IP", "2.0.0.1")


@pytest.fixture(scope="session")
def unode_client() -> UNodeClient:
    if not integration_enabled():
        pytest.skip("Set UNODE_RUN_INTEGRATION=1 to run hardware integration tests")

    client = UNodeClient(
        os.environ.get("UNODE_BASE_URL", "http://2.0.0.1"),
        os.environ.get("UNODE_PASSWORD") or None,
    )
    client.ensure_authenticated()
    return client


@pytest.fixture(scope="session")
def rp2040_port() -> str:
    port = os.environ.get("UNODE_RP2040_PORT", "")
    if not port:
        pytest.skip("Set UNODE_RP2040_PORT to run RP2040 DMX hardware tests")
    if port.lower() == "auto":
        matches = [
            candidate.device
            for candidate in list_ports.comports()
            if candidate.vid == 0x2E8A
        ]
        if not matches:
            pytest.skip("No RP2040 USB serial port found for DMX hardware tests")
        if len(matches) > 1:
            pytest.skip(
                "Multiple RP2040 USB serial ports found; set UNODE_RP2040_PORT explicitly"
            )
        return matches[0]
    return port


@pytest.fixture()
def rp2040_tool(rp2040_port: str) -> Iterator[Rp2040DmxTool]:
    step(f"Opening RP2040 DMX tool on {rp2040_port}")
    with Rp2040DmxTool(rp2040_port) as tool:
        yield tool


@pytest.fixture()
def preserved_config(unode_client: UNodeClient) -> Iterator[dict]:
    step("Saving original config for automatic restore")
    original = unode_client.get_config()
    try:
        yield original.copy()
    finally:
        step("Restoring original config")
        unode_client.save_config(original)
        # Give live-applied settings a brief moment to settle.
        time.sleep(0.2)
