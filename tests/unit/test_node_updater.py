from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "nodered" / "node_updater.py"
FLOW_PATH = PROJECT_ROOT / "tools" / "nodered" / "unode-dashboard-flow.json"
SPEC = importlib.util.spec_from_file_location("unode_node_updater", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
node_updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(node_updater)


def test_node_red_flow_contains_capability_aware_led_controls() -> None:
    flow = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in flow["nodes"]}
    configs = {config["id"]: config for config in flow["configs"]}

    template = nodes["a11e000000000129"]
    validator = nodes["a11e000000000130"]
    led_group = configs["a11e000000000212"]
    hardware_page = configs["a11e000000000213"]
    assert template["name"] == "WS2812 LED control"
    assert "ledColorOverrideSupported" in template["format"]
    assert "Legacy hardware" in template["format"]
    assert "led-set" in validator["func"]
    assert "led-release" in validator["func"]
    assert hardware_page["name"] == "Hardware Test"
    assert hardware_page["path"] == "/hardware-test"
    assert led_group["page"] == hardware_page["id"]


def test_node_red_flow_exposes_controlled_reconnection_test() -> None:
    flow = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in flow["nodes"]}
    configs = {config["id"]: config for config in flow["configs"]}

    template = nodes["a11e000000000132"]
    validator = nodes["a11e000000000133"]
    group = configs["a11e000000000214"]
    hardware_page = configs["a11e000000000213"]

    assert template["group"] == group["id"]
    assert group["page"] == hardware_page["id"]
    assert "Start Reconnection Test" in template["format"]
    assert "start-reconnect" in validator["func"]
    assert validator["wires"] == [["a11e000000000111"]]


def test_split_nmcli_fields_preserves_escaped_colons_and_backslashes() -> None:
    fields = node_updater.split_nmcli_fields(
        r"*:uNode_ABC123:87:WPA2\:WPA3\\Personal"
    )

    assert fields == ["*", "uNode_ABC123", "87", "WPA2:WPA3\\Personal"]


def test_inventory_disconnects_active_unode_before_scanning_and_restores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple] = []

    class FakeJob:
        def __init__(self) -> None:
            self.data = {}

        def progress(self, message: str, *, percent: int | None = None) -> None:
            events.append(("progress", message, percent))

        def write(self) -> None:
            events.append(("write",))

    monkeypatch.setattr(
        node_updater,
        "current_connection",
        lambda: "uNode_ABC123",
    )
    monkeypatch.setattr(
        node_updater,
        "run_nmcli",
        lambda *arguments, **_kwargs: events.append(("nmcli", *arguments)) or "",
    )
    monkeypatch.setattr(node_updater.time, "sleep", lambda _seconds: None)

    def scan() -> list[dict]:
        events.append(("scan",))
        return []

    monkeypatch.setattr(node_updater, "scan_access_points", scan)
    monkeypatch.setattr(
        node_updater,
        "restore_connection",
        lambda name: events.append(("restore", name)),
    )

    assert node_updater.inventory(FakeJob()) == []

    disconnect_index = events.index(
        ("nmcli", "--wait", "20", "connection", "down", "id", "uNode_ABC123")
    )
    scan_index = events.index(("scan",))
    restore_index = events.index(("restore", "uNode_ABC123"))
    assert disconnect_index < scan_index < restore_index


def test_restore_connection_returns_initially_idle_wifi_to_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        node_updater,
        "current_connection",
        lambda: "uNode_ABC123",
    )
    monkeypatch.setattr(
        node_updater,
        "run_nmcli",
        lambda *arguments, **_kwargs: calls.append(arguments) or "",
    )

    node_updater.restore_connection("")

    assert calls == [("device", "disconnect", node_updater.WIFI_INTERFACE)]


def test_connect_node_creates_private_user_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(node_updater, "current_connection", lambda: "--")
    monkeypatch.setattr(
        node_updater.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr(
        node_updater,
        "run_nmcli",
        lambda *arguments, **_kwargs: calls.append(arguments) or "",
    )

    node_updater.connect_node("uNode_ABC123")

    assert calls == [
        (
            "--wait",
            "20",
            "device",
            "wifi",
            "connect",
            "uNode_ABC123",
            "password",
            "artnodeABC123",
            "ifname",
            node_updater.WIFI_INTERFACE,
            "name",
            "uNode_ABC123",
            "private",
            "yes",
        )
    ]


def test_led_control_applies_colors_and_restores_previous_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple] = []

    class FakeJob:
        def __init__(self) -> None:
            self.data = {
                "nodes": [
                    {
                        "ssid": "uNode_ABC123",
                        "ledOverrideActive": False,
                    }
                ]
            }

        def progress(self, message: str, *, percent: int | None = None) -> None:
            events.append(("progress", message, percent))

    class FakeClient:
        token = ""

        def ensure_authenticated(self) -> None:
            events.append(("authenticate",))

        def post_json(self, path: str, payload: dict | None = None) -> tuple[int, bytes]:
            events.append(("post", path, payload))
            return (
                200,
                json.dumps(
                    {
                        "overrideActive": True,
                        "network": {"hex": "#123456"},
                        "activity": {"hex": "#ABCDEF"},
                    }
                ).encode(),
            )

    monkeypatch.setattr(node_updater, "current_connection", lambda: "IllumiNet")
    monkeypatch.setattr(
        node_updater,
        "connect_node",
        lambda ssid: events.append(("connect", ssid)),
    )
    monkeypatch.setattr(
        node_updater,
        "probe_node",
        lambda: {
            "chipId": "ABC123",
            "recoveryMode": False,
            "inferredProfile": "normal",
            "ledColorOverrideSupported": True,
        },
    )
    monkeypatch.setattr(node_updater, "UNodeClient", lambda *_args, **_kwargs: FakeClient())
    monkeypatch.setattr(
        node_updater,
        "restore_connection",
        lambda name: events.append(("restore", name)),
    )

    job = FakeJob()
    result = node_updater.perform_led_control(
        job,
        {
            "action": "led-set",
            "ssid": "uNode_ABC123",
            "network": "#123456",
            "activity": "#abcdef",
        },
    )

    assert result["action"] == "led-set"
    assert (
        "post",
        "/api/leds",
        {"network": "#123456", "activity": "#ABCDEF"},
    ) in events
    assert events[-1] == ("restore", "IllumiNet")
    assert job.data["nodes"][0]["ledOverrideActive"] is True


def test_led_control_rejects_legacy_hardware_and_restores_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: list[str] = []

    class FakeJob:
        data = {"nodes": []}

        def progress(self, _message: str, *, percent: int | None = None) -> None:
            del percent

    monkeypatch.setattr(node_updater, "current_connection", lambda: "IllumiNet")
    monkeypatch.setattr(node_updater, "connect_node", lambda _ssid: None)
    monkeypatch.setattr(
        node_updater,
        "probe_node",
        lambda: {
            "chipId": "ABC123",
            "recoveryMode": False,
            "inferredProfile": "legacy",
            "ledColorOverrideSupported": False,
        },
    )
    monkeypatch.setattr(
        node_updater,
        "restore_connection",
        lambda name: restored.append(name),
    )

    with pytest.raises(RuntimeError, match="Legacy hardware"):
        node_updater.perform_led_control(
            FakeJob(),
            {"action": "led-release", "ssid": "uNode_ABC123"},
        )

    assert restored == ["IllumiNet"]


@pytest.mark.parametrize("value", ["123456", "#12345", "#GG0000", "#1234567"])
def test_normalize_rgb_color_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        node_updater.normalize_rgb_color(value, "LED color")


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


def test_serial_programmers_prefers_cp210x_and_excludes_rp2040(
    tmp_path: Path,
) -> None:
    cp2102 = tmp_path / "ttyUSB1"
    ch340 = tmp_path / "ttyUSB0"
    rp2040 = tmp_path / "ttyACM0"
    cp2102.touch()
    ch340.touch()
    rp2040.touch()
    ports = [
        SimpleNamespace(
            device=str(cp2102),
            vid=0x10C4,
            pid=0xEA60,
            product="CP2102 USB to UART Bridge Controller",
            description="CP2102",
            manufacturer="Silicon Labs",
            serial_number="PRODUCTION",
        ),
        SimpleNamespace(
            device=str(ch340),
            vid=0x1A86,
            pid=0x7523,
            product="USB Serial",
            description="CH340",
            manufacturer="QinHeng",
            serial_number=None,
        ),
        SimpleNamespace(
            device=str(rp2040),
            vid=0x2E8A,
            pid=0x0003,
            product="RP2040 Zero",
            description="RP2040 Zero",
            manufacturer="Waveshare",
            serial_number="ABC123",
        ),
    ]

    devices = node_updater.serial_programmers(tmp_path / "missing", ports)

    assert devices[0]["device"] == str(cp2102)
    assert devices[0]["recommended"] is True
    assert devices[0]["supported"] is True
    assert devices[0]["vidPid"] == "10C4:EA60"
    assert devices[1]["device"] == str(ch340)
    assert devices[1]["recommended"] is False
    assert devices[1]["supported"] is True
    assert devices[2]["isRp2040"] is True
    assert devices[2]["supported"] is False


def test_esptool_output_parsers_read_chip_id_mac_and_flash_capacity() -> None:
    assert node_updater.parse_esp8266_chip_id("Chip ID: 0x005d33bc") == "5D33BC"
    assert (
        node_updater.parse_esp8266_chip_id("MAC: 48:3f:da:5d:33:bc")
        == "5D33BC"
    )
    assert (
        node_updater.parse_flash_size("Auto-detected flash size: 4MB")
        == 4 * 1024 * 1024
    )
    assert (
        node_updater.parse_flash_size("Detected flash size: 4096KB")
        == 4 * 1024 * 1024
    )


def test_esptool_output_parsers_reject_missing_identity_and_capacity() -> None:
    with pytest.raises(RuntimeError, match="chip ID"):
        node_updater.parse_esp8266_chip_id("Connected to ESP8266")
    with pytest.raises(RuntimeError, match="flash capacity"):
        node_updater.parse_flash_size("Manufacturer: ef")


def test_initial_flash_uses_verified_release_offsets_and_factory_ap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    firmware = tmp_path / "firmware.bin"
    littlefs = tmp_path / "littlefs.bin"
    firmware.write_bytes(b"firmware")
    littlefs.write_bytes(b"littlefs")
    (tmp_path / "uNode-0.23.23-manifest.json").write_text(
        json.dumps({"version": "0.23.23", "flashLayout": "4M1M"}),
        encoding="utf-8",
    )
    artifacts = SimpleNamespace(
        firmware=firmware,
        littlefs=littlefs,
        firmware_sha256="A" * 64,
        littlefs_sha256="B" * 64,
    )
    calls: list[list[str]] = []

    def fake_esptool(
        _job: object,
        _port: str,
        arguments: list[str],
        **_kwargs: object,
    ) -> str:
        calls.append(arguments)
        if arguments[0] == "chip-id":
            return "Chip ID: 0x005d33bc"
        if arguments[0] == "flash-id":
            return "Detected flash size: 4MB"
        return "Hash of data verified.\nHash of data verified."

    monkeypatch.setattr(
        node_updater,
        "resolve_release_artifacts",
        lambda *args, **kwargs: artifacts,
    )
    monkeypatch.setattr(node_updater, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(
        node_updater,
        "resolve_serial_programmer",
        lambda _port: {
            "stablePath": "/dev/serial/by-id/test-programmer",
            "description": "Test CH340",
        },
    )
    monkeypatch.setattr(node_updater, "run_esptool", fake_esptool)
    monkeypatch.setattr(
        node_updater,
        "wait_for_factory_ap",
        lambda chip_id: {"ssid": f"uNode_{chip_id}", "signal": 88},
    )
    job = SimpleNamespace(data={}, progress=lambda *_args, **_kwargs: None)

    result = node_updater.perform_initial_flash(
        job,
        {
            "version": "0.23.23",
            "profile": "normal",
            "port": "/dev/serial/by-id/test-programmer",
            "eraseAll": False,
        },
    )

    assert result["chipId"] == "5D33BC"
    assert result["verifiedBlocks"] == 2
    assert [call[0] for call in calls] == ["chip-id", "flash-id", "write-flash"]
    assert calls[2][-4:] == [
        "0x000000",
        str(firmware),
        "0x300000",
        str(littlefs),
    ]


@pytest.mark.parametrize("version", ["v0.23.23", "0.23", "0.23.23-beta", "../../x"])
def test_version_key_rejects_non_release_strings(version: str) -> None:
    with pytest.raises(ValueError):
        node_updater.version_key(version)
