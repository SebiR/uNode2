from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "fixture_reconnection.py"
SPEC = importlib.util.spec_from_file_location("unode_fixture_reconnection", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
fixture_reconnection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_reconnection)


def test_hotspot_profile_is_ephemeral_and_uses_networkmanager_shared_mode(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        fixture_reconnection,
        "_nmcli",
        lambda *arguments, **_kwargs: calls.append(arguments) or "",
    )

    fixture_reconnection._prepare_hotspot_profile(
        "wlan0",
        "uNode-Fixture-Hotspot",
        "uNode-Fixture",
        "uNodeFixture24",
    )

    assert calls[0] == (
        "connection",
        "delete",
        "id",
        "uNode-Fixture-Hotspot",
    )
    assert "autoconnect" in calls[1]
    assert calls[1][calls[1].index("autoconnect") + 1] == "no"
    assert "ipv4.method" in calls[2]
    assert calls[2][calls[2].index("ipv4.method") + 1] == "shared"


def test_pytest_child_receives_discovered_ip_and_auth_password(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(fixture_reconnection.subprocess, "run", fake_run)
    client = SimpleNamespace(
        base_url="http://10.42.0.23",
        password="fixture-admin",
    )

    assert fixture_reconnection._run_pytest(client) == 0
    environment = captured["environment"]
    assert environment["UNODE_IP"] == "10.42.0.23"
    assert environment["UNODE_BASE_URL"] == "http://10.42.0.23"
    assert environment["UNODE_PASSWORD"] == "fixture-admin"
    assert "tests/integration/test_network_reconnection.py" in captured["command"]
