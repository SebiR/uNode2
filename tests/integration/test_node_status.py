from __future__ import annotations

from helpers import step
from unode_client import UNodeClient


def test_status_endpoint_reports_expected_basics(unode_client: UNodeClient) -> None:
    step("Reading /api/status")
    status = unode_client.get_json("/api/status")
    step(
        "Status received: "
        f"firmware={status['firmware']}, chip={status['chipId']}, "
        f"uptime={status['uptime']} ms"
    )

    assert status["firmware"]
    assert status["chipId"]
    assert status["flashLayout"] == "4M1M"
    assert isinstance(status["uptime"], int)
    assert isinstance(status["artNetDiagnostics"], dict)
