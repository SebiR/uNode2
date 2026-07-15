from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "check_unode.py"
SPEC = importlib.util.spec_from_file_location("check_unode", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_unode = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_unode)


def test_preflight_retries_then_returns_identified_node(monkeypatch) -> None:
    attempts = 0

    def read_status(_base_url: str, _timeout: float) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("fixture not associated yet")
        return {"name": "IN_uNode", "chipId": "ABC123", "firmware": "0.25.0"}

    monkeypatch.setattr(check_unode, "_read_status", read_status)
    monkeypatch.setattr(check_unode.time, "sleep", lambda _seconds: None)

    status = check_unode.wait_for_unode(
        "http://2.0.0.1",
        attempts=3,
        timeout=0.1,
        interval=0.0,
    )

    assert status["chipId"] == "ABC123"
    assert attempts == 3


def test_preflight_reports_bounded_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        check_unode,
        "_read_status",
        lambda _base_url, _timeout: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    monkeypatch.setattr(check_unode.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        check_unode.wait_for_unode(
            "http://2.0.0.1",
            attempts=2,
            timeout=0.1,
            interval=0.0,
        )
