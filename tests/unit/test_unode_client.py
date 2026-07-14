from __future__ import annotations

import json

from unode_client import UNodeClient


def _json_response(value: dict) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(value).encode("utf-8")


def test_authenticated_test_client_uses_protected_diagnostics_for_status(
    monkeypatch,
) -> None:
    client = UNodeClient("http://2.0.0.1")
    client.prefer_detailed_status = True
    paths: list[str] = []

    def request(method: str, path: str, **_kwargs):
        paths.append(path)
        return _json_response({"detailed": True})

    monkeypatch.setattr(client, "_request", request)

    assert client.get_json("/api/status?probe=1")["detailed"] is True
    assert paths == ["/api/diagnostics?probe=1"]


def test_detailed_status_falls_back_to_recovery_status_on_404(monkeypatch) -> None:
    client = UNodeClient("http://2.0.0.1")
    client.prefer_detailed_status = True
    paths: list[str] = []

    def request(method: str, path: str, **_kwargs):
        paths.append(path)
        if path == "/api/diagnostics":
            return 404, "text/plain", b"Not found"
        return _json_response({"recoveryMode": True})

    monkeypatch.setattr(client, "_request", request)

    assert client.get_json("/api/status")["recoveryMode"] is True
    assert paths == ["/api/diagnostics", "/api/status"]
