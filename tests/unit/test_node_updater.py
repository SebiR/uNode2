from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "nodered" / "node_updater.py"
SPEC = importlib.util.spec_from_file_location("unode_node_updater", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
node_updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(node_updater)


def test_split_nmcli_fields_preserves_escaped_colons_and_backslashes() -> None:
    fields = node_updater.split_nmcli_fields(
        r"*:uNode_ABC123:87:WPA2\:WPA3\\Personal"
    )

    assert fields == ["*", "uNode_ABC123", "87", "WPA2:WPA3\\Personal"]


def test_decode_request_accepts_urlsafe_json_and_rejects_non_objects() -> None:
    request = {
        "action": "update",
        "ssid": "uNode_ABC123",
        "version": "0.23.23",
    }
    encoded = base64.urlsafe_b64encode(json.dumps(request).encode()).decode().rstrip("=")

    assert node_updater.decode_request(encoded) == request

    encoded_list = base64.urlsafe_b64encode(b"[]").decode().rstrip("=")
    with pytest.raises(ValueError, match="JSON object"):
        node_updater.decode_request(encoded_list)


def test_available_releases_lists_only_complete_profiles_newest_first(
    tmp_path: Path,
) -> None:
    def add_release(version: str, *, normal: bool, legacy: bool) -> None:
        profiles = {}
        for profile, enabled in (("normal", normal), ("legacy", legacy)):
            suffix = "" if profile == "normal" else "_legacy"
            firmware_name = f"uNode-{version}{suffix}-firmware.bin"
            littlefs_name = f"uNode-{version}{suffix}-littlefs.bin"
            firmware = tmp_path / firmware_name
            littlefs = tmp_path / littlefs_name
            if enabled:
                firmware.write_bytes(b"firmware")
                littlefs.write_bytes(b"littlefs")
            profiles[profile] = {
                "firmware": {
                    "file": firmware_name,
                    "size": 8,
                    "sha256": "A" * 64,
                },
                "littleFs": {
                    "file": littlefs_name,
                    "size": 8,
                    "sha256": "B" * 64,
                },
            }
        manifest = {
            "version": version,
            "generatedAt": "2026-07-14T00:00:00Z",
            "profiles": profiles,
        }
        (tmp_path / f"uNode-{version}-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    add_release("0.23.22", normal=True, legacy=False)
    add_release("0.23.23", normal=True, legacy=True)
    add_release("0.24.0", normal=False, legacy=False)

    releases = node_updater.available_releases(tmp_path)

    assert [item["version"] for item in releases] == ["0.23.23", "0.23.22"]
    assert set(releases[0]["profiles"]) == {"normal", "legacy"}
    assert releases[1]["profiles"] == ["normal"]


def test_idle_status_reports_fixture_lock_and_clears_stale_busy_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "running": False,
                "state": "error",
                "message": (
                    "The uNode test fixture is busy with a regression or soak job"
                ),
                "progress": 25,
                "nodes": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(node_updater, "STATUS_FILE", status_path)
    monkeypatch.setattr(node_updater, "available_releases", lambda: [])
    monkeypatch.setattr(node_updater, "fixture_is_busy", lambda: True)

    busy = node_updater.idle_status()

    assert busy["fixtureBusy"] is True
    assert busy["state"] == "error"

    monkeypatch.setattr(node_updater, "fixture_is_busy", lambda: False)
    idle = node_updater.idle_status()

    assert idle["fixtureBusy"] is False
    assert idle["state"] == "idle"
    assert idle["progress"] == 0
    assert idle["message"] == "Ready to scan for uNode access points"


@pytest.mark.parametrize("version", ["v0.23.23", "0.23", "0.23.23-beta", "../../x"])
def test_version_key_rejects_non_release_strings(version: str) -> None:
    with pytest.raises(ValueError):
        node_updater.version_key(version)
