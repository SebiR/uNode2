from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from helpers import step
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
