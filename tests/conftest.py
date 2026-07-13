from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from serial.tools import list_ports

from helpers import step
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient

_TEST_REPORTS: dict[str, dict[str, object]] = {}
_SESSION_STARTED_AT = datetime.now(timezone.utc)
_NODE_STATUS_SNAPSHOT: dict[str, object] = {}
_RP2040_INFO: dict[str, object] = {
    "configuredPort": os.environ.get("UNODE_RP2040_PORT", ""),
    "port": "",
    "firmware": "",
    "mode": "",
    "auxGpioPins": [],
}


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


def _project_root(config: pytest.Config) -> Path:
    root = getattr(config, "rootpath", None)
    if root is not None:
        return Path(root)
    return Path(str(config.rootdir))


def _load_report_mapping(config: pytest.Config) -> dict[str, dict[str, str]]:
    mapping_path = _project_root(config) / "tests" / "report_mapping.en.json"
    try:
        return json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _mapped_test_info(
    mapping: dict[str, dict[str, str]],
    nodeid: str,
) -> dict[str, str]:
    info = mapping.get(nodeid, {})
    return {
        "group": info.get("group", "Other"),
        "title": info.get("title", nodeid.split("::")[-1]),
        "description": info.get("description", ""),
    }


def _safe_filename_part(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    return text.strip("-._")


def _format_rp2040_info() -> str:
    port = str(
        _RP2040_INFO.get("port")
        or _RP2040_INFO.get("configuredPort")
        or ""
    ).strip()
    firmware = str(_RP2040_INFO.get("firmware") or "").strip()
    mode = str(_RP2040_INFO.get("mode") or "").strip()
    aux_gpio_pins = _RP2040_INFO.get("auxGpioPins")

    parts: list[str] = []
    if port:
        parts.append(port)
    if firmware:
        parts.append(f"FW {firmware}")
    if mode:
        parts.append(f"mode {mode}")
    if isinstance(aux_gpio_pins, list) and aux_gpio_pins:
        pins = ", ".join(str(pin) for pin in aux_gpio_pins)
        parts.append(f"GPIO {pins}")

    return " | ".join(parts)


def _test_report_path(config: pytest.Config, node_status: dict) -> Path:
    configured = os.environ.get("UNODE_TEST_REPORT_JSON", "")
    if configured:
        return Path(configured)

    timestamp = _SESSION_STARTED_AT.strftime("%Y%m%d-%H%M%SZ")
    chip_id = _safe_filename_part(node_status.get("chipId", ""))
    filename = (
        f"unode-{chip_id}-test-report-{timestamp}.json"
        if chip_id
        else f"unode-test-report-{timestamp}.json"
    )
    return (
        _project_root(config)
        / "artifacts"
        / "test_reports"
        / filename
    )


def _write_json_report(
    config: pytest.Config,
    *,
    counts: dict[str, int],
    started_at: datetime,
    finished_at: datetime,
    node_status: dict,
) -> Path:
    mapping = _load_report_mapping(config)
    tests = []

    for nodeid in sorted(_TEST_REPORTS):
        result = _TEST_REPORTS[nodeid]
        mapped = _mapped_test_info(mapping, nodeid)
        tests.append(
            {
                "nodeid": nodeid,
                "group": mapped["group"],
                "title": mapped["title"],
                "description": mapped["description"],
                "status": result["status"],
                "durationSeconds": round(float(result["duration"]), 6),
                "metrics": result.get("metrics", {}),
            }
        )

    report = {
        "schemaVersion": 1,
        "project": "uNode 2",
        "startedAt": started_at.isoformat(timespec="seconds"),
        "finishedAt": finished_at.isoformat(timespec="seconds"),
        "durationSeconds": round((finished_at - started_at).total_seconds(), 3),
        "integration": integration_enabled(),
        "environment": {
            "nodeIp": os.environ.get("UNODE_IP", ""),
            "baseUrl": os.environ.get("UNODE_BASE_URL", ""),
            "rp2040Port": _RP2040_INFO.get("configuredPort", ""),
            "rp2040ResolvedPort": _RP2040_INFO.get("port", ""),
            "rp2040Firmware": _RP2040_INFO.get("firmware", ""),
            "rp2040Mode": _RP2040_INFO.get("mode", ""),
            "rp2040AuxGpioPins": _RP2040_INFO.get("auxGpioPins", []),
        },
        "node": {
            "name": node_status.get("name", ""),
            "chipId": node_status.get("chipId", ""),
            "firmware": node_status.get("firmware", ""),
            "ip": node_status.get("ip", os.environ.get("UNODE_IP", "")),
            "mac": node_status.get("mac", ""),
            "resetReason": node_status.get("resetReason", ""),
            "bootCount": node_status.get("bootCount", None),
        },
        "summary": {
            "passed": counts.get("PASSED", 0),
            "failed": counts.get("FAILED", 0),
            "skipped": counts.get("SKIPPED", 0),
            "total": sum(counts.values()),
            "result": "PASS" if counts.get("FAILED", 0) == 0 else "FAIL",
        },
        "tests": tests,
    }

    output_path = _test_report_path(config, node_status)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


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

    metrics = {}
    for name, value in getattr(report, "user_properties", []):
        if name.startswith("metric."):
            metrics[name.removeprefix("metric.")] = value

    _TEST_REPORTS[report.nodeid] = {
        "status": status,
        "duration": report.duration,
        "metrics": metrics,
    }


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    del exitstatus

    now = datetime.now().astimezone()
    finished_at = datetime.now(timezone.utc)
    terminalreporter.write_sep("=", "uNode Test Certificate")

    node_status = {}
    if integration_enabled():
        # Prefer the final live state, but retain identity and firmware details
        # captured at session start when the very failure under test leaves the
        # node or its network stack unreachable.
        node_status = {
            **_NODE_STATUS_SNAPSHOT,
            **_read_node_status(),
        }
        chip_id = node_status.get("chipId", "unknown")
        firmware = node_status.get("firmware", "unknown")
        node_name = node_status.get("name", "unknown")
        ip = node_status.get("ip", os.environ.get("UNODE_IP", "unknown"))
        terminalreporter.write_line(
            f"Node       : {node_name} {chip_id} (FW {firmware})"
        )
        terminalreporter.write_line(f"IP         : {ip}")
        rp2040 = _format_rp2040_info()
        if rp2040:
            terminalreporter.write_line(f"RP2040     : {rp2040}")
    else:
        terminalreporter.write_line("Node       : offline/unit test run")

    terminalreporter.write_line(f"Test Date  : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    terminalreporter.write_line(f"UTC        : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    terminalreporter.write_line("")

    mapping = _load_report_mapping(config)
    counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0}
    for nodeid in sorted(_TEST_REPORTS):
        result = _TEST_REPORTS[nodeid]
        status_text = str(result["status"])
        counts[status_text] = counts.get(status_text, 0) + 1
        duration = float(result["duration"])
        mapped = _mapped_test_info(mapping, nodeid)
        terminalreporter.write_line(
            f"[{status_text:<7}] {mapped['group']} / {mapped['title']} "
            f"({duration:.2f}s)"
        )

    terminalreporter.write_line("")
    terminalreporter.write_line(
        "Summary    : "
        f"{counts.get('PASSED', 0)} passed, "
        f"{counts.get('FAILED', 0)} failed, "
        f"{counts.get('SKIPPED', 0)} skipped"
    )

    if not getattr(config.option, "collectonly", False):
        report_path = _write_json_report(
            config,
            counts=counts,
            started_at=_SESSION_STARTED_AT,
            finished_at=finished_at,
            node_status=node_status,
        )
        terminalreporter.write_line(f"JSON Report: {report_path}")


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
    try:
        _NODE_STATUS_SNAPSHOT.update(client.get_json("/api/status"))
    except Exception:  # noqa: BLE001 - test setup reports the real error later.
        pass
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
        _RP2040_INFO["port"] = rp2040_port
        ping = tool.ping()
        _RP2040_INFO["firmware"] = str(ping.get("fw", ""))
        _RP2040_INFO["mode"] = str(ping.get("mode", ""))
        aux_gpio_pins = ping.get("auxGpioPins", [])
        _RP2040_INFO["auxGpioPins"] = (
            aux_gpio_pins if isinstance(aux_gpio_pins, list) else []
        )
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
