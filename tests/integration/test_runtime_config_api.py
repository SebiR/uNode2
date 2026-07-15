from __future__ import annotations

import pytest

from helpers import step, wait_for_node_restart, wait_for_status
from unode_client import UNodeClient


RUNTIME_FIELDS = (
    "liveProtocol",
    "direction",
    "mergeMode",
    "failsafeMode",
    "legacyArtPollReply",
)


def test_test_harness_runtime_config_is_live_and_non_persistent(
    unode_client: UNodeClient,
) -> None:
    """Prove that soak configuration changes stay in RAM without persisting."""

    before = unode_client.get_json("/api/status")
    diagnostics = before.get("networkDiagnostics", {})
    if not diagnostics.get("testHarnessApiEnabled", False):
        pytest.skip("Runtime config API requires ENABLE_TEST_HARNESS_API=1")

    unode_client.ensure_authenticated()
    original = unode_client.get_config()
    candidate = original.copy()
    candidate["liveProtocol"] = 1 - int(original.get("liveProtocol", 0))
    candidate["direction"] = 1 - int(original.get("direction", 0))
    candidate["mergeMode"] = 1 - int(original.get("mergeMode", 0))
    candidate["failsafeMode"] = (int(original.get("failsafeMode", 0)) + 1) % 4
    candidate["legacyArtPollReply"] = not bool(
        original.get("legacyArtPollReply", False)
    )
    initial_boot_count = int(before["bootCount"])

    step("Rejecting unsupported and out-of-range runtime configuration")
    for payload in ({"hostname": "must-not-change"}, {"liveProtocol": 99}):
        status_code, body = unode_client.post_json(
            "/api/test/runtime-config",
            payload,
        )
        assert status_code == 400, body.decode(errors="replace")

    unchanged = unode_client.get_config()
    for key in RUNTIME_FIELDS:
        assert unchanged[key] == original[key], f"{key} changed after invalid input"

    step("Applying volatile test-harness runtime configuration")
    response = unode_client.apply_runtime_config(candidate)
    assert response["appliedLive"] is True
    assert response["persistent"] is False

    active = wait_for_status(
        unode_client,
        lambda status: all(status.get(key) == candidate[key] for key in RUNTIME_FIELDS),
    )
    assert int(active["bootCount"]) == initial_boot_count

    step("Restarting to prove that temporary runtime values were not persisted")
    restart_status, body = unode_client.post_json("/api/restart")
    assert restart_status == 200, body.decode(errors="replace")

    restarted = wait_for_node_restart(
        unode_client,
        previous_boot_count=initial_boot_count,
    )
    assert int(restarted["bootCount"]) > initial_boot_count

    persisted = unode_client.get_config()
    for key in RUNTIME_FIELDS:
        assert persisted[key] == original[key], f"{key} unexpectedly persisted"
