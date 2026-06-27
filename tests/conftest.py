from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest
from serial.tools import list_ports

from helpers import step
from rp2040_dmx_tool import Rp2040DmxTool
from unode_client import UNodeClient


def integration_enabled() -> bool:
    return os.environ.get("UNODE_RUN_INTEGRATION") == "1"


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
