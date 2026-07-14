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
    assert isinstance(status["artNetSources"], list)
    assert isinstance(status["sacnDiagnostics"], dict)
    assert isinstance(status["networkDiagnostics"], dict)
    assert isinstance(status["ledOverrideActive"], bool)
    assert isinstance(status["ledColorOverrideSupported"], bool)
    assert status["ledColorOverrideSupported"] is (
        status.get("ledHardware") == "WS2812"
    )

    network_diagnostics = status["networkDiagnostics"]
    assert network_diagnostics["ipFragmentGuardEnabled"] is True
    assert isinstance(network_diagnostics["ipv4FragmentsDropped"], int)
    assert network_diagnostics["ipv4FragmentsDropped"] >= 0
    assert isinstance(network_diagnostics["ipv4FragmentedTxRejected"], int)
    assert network_diagnostics["ipv4FragmentedTxRejected"] >= 0
    assert isinstance(network_diagnostics["reconnectAttemptsTotal"], int)
    assert network_diagnostics["reconnectAttemptsTotal"] >= 0
    assert isinstance(network_diagnostics["reconnectSuccesses"], int)
    assert network_diagnostics["reconnectSuccesses"] >= 0
    assert isinstance(network_diagnostics["lastReconnectDuration"], int)
    assert network_diagnostics["lastReconnectDuration"] >= 0
    assert isinstance(network_diagnostics["testHarnessApiEnabled"], bool)
    if network_diagnostics["testHarnessApiEnabled"]:
        assert isinstance(
            network_diagnostics["temporaryTestClientActive"],
            bool,
        )

    for key in (
        "multicastJoined",
        "multicastJoins",
        "multicastLeaves",
        "multicastJoinFailures",
        "multicastLeaveFailures",
        "socketRebinds",
    ):
        assert key in status["sacnDiagnostics"]

    for source in status["artNetSources"]:
        assert isinstance(source["ip"], str)
        assert isinstance(source["name"], str)
        assert isinstance(source["physical"], int)
        assert isinstance(source["lastSeenAge"], int)
        assert isinstance(source["winning"], bool)
