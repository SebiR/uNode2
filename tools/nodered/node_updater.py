#!/usr/bin/env python3
"""Discover uNode access points and install verified release artifacts.

The helper is designed for the Raspberry Pi production/test fixture. Ethernet
keeps Node-RED reachable while ``wlan0`` is temporarily connected to one uNode
access point at a time. Commands are deliberately narrow and every SSID,
release version, hardware profile, and update component is validated before it
is passed to NetworkManager or the OTA client.
"""

from __future__ import annotations

import base64
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from serial.tools import list_ports

try:
    import fcntl
except ModuleNotFoundError:  # pragma: no cover - updater jobs run on Linux.
    fcntl = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = PROJECT_ROOT / "tests"
sys.path.insert(0, str(TESTS_ROOT))

from ota_helpers import resolve_release_artifacts, upload_file  # noqa: E402
from unode_client import UNodeClient  # noqa: E402


ARTIFACTS_DIR = Path(
    os.environ.get(
        "UNODE_UPDATER_ARTIFACTS_DIR",
        PROJECT_ROOT / "artifacts" / "release",
    )
)
BACKUP_DIR = Path(
    os.environ.get(
        "UNODE_UPDATER_BACKUP_DIR",
        PROJECT_ROOT / "artifacts" / "node_backups",
    )
)
STATUS_FILE = Path(
    os.environ.get("UNODE_UPDATER_STATUS_FILE", "/tmp/unode-updater-status.json")
)
LOCK_FILE = Path(
    os.environ.get("UNODE_UPDATER_LOCK_FILE", "/tmp/unode-updater.lock")
)
TEST_JOB_LOCK_FILE = Path(
    os.environ.get("UNODE_TEST_JOB_LOCK_FILE", "/tmp/unode-test-job.lock")
)
LOG_FILE = Path(
    os.environ.get(
        "UNODE_UPDATER_LOG_FILE",
        PROJECT_ROOT / "artifacts" / "test_reports" / "latest-updater.log",
    )
)
WIFI_INTERFACE = os.environ.get("UNODE_UPDATER_WIFI_INTERFACE", "wlan0")
NODE_IP = os.environ.get("UNODE_UPDATER_NODE_IP", "2.0.0.1")
BASE_URL = f"http://{NODE_IP}"
SERIAL_BY_ID_DIR = Path(
    os.environ.get("UNODE_UPDATER_SERIAL_BY_ID_DIR", "/dev/serial/by-id")
)

SSID_PATTERN = re.compile(r"^uNode_([0-9A-Fa-f]{6})$")
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
ALLOWED_PROFILES = {"normal", "legacy", "gpio_fix"}
ALLOWED_COMPONENTS = {"firmware", "littlefs", "both"}
FLASH_BAUD = 512_000
FIRMWARE_ADDRESS = 0x000000
LITTLEFS_ADDRESS = 0x300000
EXPECTED_FLASH_BYTES = 4 * 1024 * 1024
CP210X_DEFAULT_VID_PID = (0x10C4, 0xEA60)
RGB_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for status files."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace one JSON status file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def persisted_node_inventory() -> list[dict[str, Any]]:
    """Return the most recent node list without trusting malformed state."""

    if not STATUS_FILE.is_file():
        return []
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        nodes = status.get("nodes", []) if isinstance(status, dict) else []
        if isinstance(nodes, list) and all(isinstance(node, dict) for node in nodes):
            return nodes
    except (OSError, json.JSONDecodeError):
        pass
    return []


def persisted_access_points() -> list[dict[str, Any]]:
    """Return the most recent lightweight dashboard Wi-Fi scan."""

    if not STATUS_FILE.is_file():
        return []
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        access_points = (
            status.get("accessPoints", []) if isinstance(status, dict) else []
        )
        if isinstance(access_points, list) and all(
            isinstance(access_point, dict) for access_point in access_points
        ):
            return access_points
    except (OSError, json.JSONDecodeError):
        pass
    return []


def split_nmcli_fields(line: str) -> list[str]:
    """Split one escaped ``nmcli -t`` record without losing literal colons."""

    fields: list[str] = []
    current: list[str] = []
    escaped = False

    for character in line.rstrip("\r\n"):
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)

    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def version_key(version: str) -> tuple[int, int, int]:
    """Return a sortable semantic-version tuple for supported releases."""

    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise ValueError(f"Invalid release version: {version}")
    return tuple(int(value) for value in match.groups())


def available_releases(root: Path = ARTIFACTS_DIR) -> list[dict[str, Any]]:
    """Return complete release profiles newest first.

    This lightweight listing is generated on every dashboard status poll and
    therefore verifies manifest sizes without repeatedly hashing megabytes of
    artifacts. ``resolve_release_artifacts()`` performs the full SHA-256 check
    immediately before any update is written.
    """

    releases: list[dict[str, Any]] = []
    for manifest_path in root.glob("uNode-*-manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            version = str(manifest["version"])
            version_key(version)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue

        profiles: list[str] = []
        for profile in sorted(ALLOWED_PROFILES):
            profile_data = manifest.get("profiles", {}).get(profile, {})
            firmware_data = profile_data.get("firmware", {})
            littlefs_data = profile_data.get("littleFs", {})
            firmware = root / str(firmware_data.get("file", ""))
            littlefs = root / str(littlefs_data.get("file", ""))

            try:
                valid = (
                    firmware.is_file()
                    and littlefs.is_file()
                    and firmware.stat().st_size == int(firmware_data["size"])
                    and littlefs.stat().st_size == int(littlefs_data["size"])
                    and bool(str(firmware_data["sha256"]))
                    and bool(str(littlefs_data["sha256"]))
                )
            except (KeyError, TypeError, ValueError, OSError):
                valid = False

            if valid:
                profiles.append(profile)

        if profiles:
            releases.append(
                {
                    "version": version,
                    "profiles": profiles,
                    "generatedAt": str(manifest.get("generatedAt", "")),
                }
            )

    releases.sort(key=lambda item: version_key(item["version"]), reverse=True)
    return releases


def serial_programmers(
    by_id_root: Path = SERIAL_BY_ID_DIR,
    ports: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Return attached USB serial devices with stable Linux paths.

    RP2040 CDC devices remain visible for diagnostics but are deliberately not
    selectable as ESP programmers. CP210x adapters are preferred for the
    production fixture while the CH340 remains a fully compatible bench tool.
    """

    stable_paths: dict[str, str] = {}
    if by_id_root.is_dir():
        for candidate in by_id_root.iterdir():
            try:
                stable_paths[str(candidate.resolve(strict=True))] = str(candidate)
            except OSError:
                continue

    devices: list[dict[str, Any]] = []
    for port in ports if ports is not None else list(list_ports.comports()):
        device = str(port.device)
        try:
            resolved_device = str(Path(device).resolve(strict=True))
        except OSError:
            resolved_device = device

        vid = int(port.vid) if port.vid is not None else None
        pid = int(port.pid) if port.pid is not None else None
        product = str(port.product or port.description or "USB serial adapter")
        manufacturer = str(port.manufacturer or "")
        is_rp2040 = vid == 0x2E8A or "RP2040" in product.upper()
        stable_path = stable_paths.get(resolved_device, device)
        recommended = (
            (vid, pid) == CP210X_DEFAULT_VID_PID
            or "CP210" in product.upper()
        )
        supported = (
            not is_rp2040
            and vid is not None
            and pid is not None
            and Path(device).exists()
        )

        devices.append(
            {
                "port": stable_path,
                "device": device,
                "stablePath": stable_path,
                "description": product,
                "manufacturer": manufacturer,
                "serialNumber": str(port.serial_number or ""),
                "vid": vid,
                "pid": pid,
                "vidPid": (
                    f"{vid:04X}:{pid:04X}"
                    if vid is not None and pid is not None
                    else "unknown"
                ),
                "recommended": recommended,
                "supported": supported,
                "isRp2040": is_rp2040,
            }
        )

    return sorted(
        devices,
        key=lambda item: (
            not bool(item["recommended"]),
            not bool(item["supported"]),
            str(item["stablePath"]),
        ),
    )


def resolve_serial_programmer(requested_port: str) -> dict[str, Any]:
    """Resolve a request only against the currently attached device list."""

    if not requested_port or len(requested_port) > 256:
        raise ValueError("A serial programmer must be selected")
    matches = [
        device
        for device in serial_programmers()
        if requested_port in {device["port"], device["device"]}
    ]
    if len(matches) != 1 or not matches[0]["supported"]:
        raise ValueError(
            "Selected serial device is unavailable or not an ESP programmer"
        )
    return matches[0]


def installed_esptool_version() -> str:
    """Return the installed esptool version or an empty string."""

    try:
        return importlib.metadata.version("esptool")
    except importlib.metadata.PackageNotFoundError:
        return ""


class JobStatus:
    """Persist updater state and mirror progress into a plain-text log."""

    def __init__(self, request: dict[str, Any]) -> None:
        self.data: dict[str, Any] = {
            "running": True,
            "state": "starting",
            "message": "Starting uNode updater",
            "startedAt": utc_now(),
            "finishedAt": "",
            "request": {
                key: value
                for key, value in request.items()
                if key != "password"
            },
            "nodes": persisted_node_inventory(),
            "accessPoints": persisted_access_points(),
            "releases": available_releases(),
            "serialProgrammers": serial_programmers(),
            "progress": 0,
        }
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("", encoding="utf-8")
        self.write()

    def write(self) -> None:
        atomic_json_write(STATUS_FILE, self.data)

    def progress(self, message: str, *, percent: int | None = None) -> None:
        line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
        print(line, flush=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self.data["message"] = message
        if percent is not None:
            self.data["progress"] = max(0, min(100, int(percent)))
        self.write()

    def log_output(self, output: str) -> None:
        """Append bounded subprocess output without replacing job progress."""

        if not output:
            return
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            for line in output.rstrip().splitlines():
                handle.write(f"    {line[:500]}\n")

    def finish(self, state: str, message: str, **values: Any) -> None:
        self.data.update(values)
        self.data.update(
            {
                "running": False,
                "state": state,
                "message": message,
                "finishedAt": utc_now(),
                "progress": (
                    100
                    if state in {"ready", "updated", "flashed"}
                    else self.data["progress"]
                ),
            }
        )
        self.progress(message)


def run_nmcli(*arguments: str, timeout: float = 30.0) -> str:
    """Run one bounded NetworkManager command and return stdout."""

    result = subprocess.run(
        ["nmcli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"nmcli {' '.join(arguments)} failed: {detail}")
    return result.stdout


def current_connection() -> str:
    """Return the active NetworkManager connection on the updater interface."""

    output = run_nmcli("-g", "GENERAL.CONNECTION", "device", "show", WIFI_INTERFACE)
    return output.strip()


def disconnect_unode_for_scan(name: str) -> bool:
    """Disconnect an active uNode AP so NetworkManager scans every channel.

    Some Wi-Fi adapters return only their current ESP8266 AP while associated
    with it. Router/client connections are left alone because they normally
    permit a complete background scan and may provide intentional management
    connectivity.
    """

    if not SSID_PATTERN.fullmatch(name):
        return False

    run_nmcli("--wait", "20", "connection", "down", "id", name)
    time.sleep(1.0)
    return True


def scan_access_points() -> list[dict[str, Any]]:
    """Scan and return the strongest advertisement for every uNode AP."""

    output = run_nmcli(
        "-t",
        "--escape",
        "yes",
        "-f",
        "IN-USE,SSID,SIGNAL,SECURITY",
        "device",
        "wifi",
        "list",
        "ifname",
        WIFI_INTERFACE,
        "--rescan",
        "yes",
        timeout=45.0,
    )
    nodes: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        fields = split_nmcli_fields(line)
        if len(fields) < 4:
            continue
        active, ssid, signal, security = fields[:4]
        match = SSID_PATTERN.fullmatch(ssid)
        if not match:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        candidate = {
            "ssid": ssid,
            "chipId": match.group(1).upper(),
            "signal": strength,
            "security": security or "Open",
            "active": active == "*",
        }
        previous = nodes.get(ssid)
        if previous is None or strength > int(previous["signal"]):
            nodes[ssid] = candidate

    return sorted(nodes.values(), key=lambda item: (-int(item["signal"]), item["ssid"]))


def scan_for_dashboard_connection(job: JobStatus) -> list[dict[str, Any]]:
    """Perform a lightweight AP scan without changing the active connection."""

    job.data["state"] = "scanning"
    job.progress("Scanning wlan0 for uNode access points", percent=10)
    access_points = scan_access_points()
    job.data["accessPoints"] = access_points
    job.progress(
        f"Found {len(access_points)} uNode access point(s)",
        percent=90,
    )
    return access_points


def connect_dashboard_node(
    job: JobStatus, request: dict[str, Any]
) -> dict[str, Any]:
    """Connect the fixture Wi-Fi to one advertised uNode and leave it active."""

    ssid = str(request.get("ssid", ""))
    expected_chip = validate_ssid(ssid).group(1).upper()

    job.data["state"] = "connecting"
    job.progress(f"Checking that {ssid} is still available", percent=10)
    access_points = scan_access_points()
    selected = next(
        (item for item in access_points if item.get("ssid") == ssid),
        None,
    )
    if selected is None:
        raise RuntimeError(f"{ssid} is no longer visible on wlan0")

    job.data["accessPoints"] = access_points
    job.progress(f"Connecting wlan0 to {ssid}", percent=35)
    connect_node(ssid)
    job.progress(f"Waiting for the uNode API at {BASE_URL}", percent=65)
    node = probe_node()
    actual_chip = str(node.get("chipId", "")).upper()
    if actual_chip != expected_chip:
        raise RuntimeError(
            f"Connected AP identity mismatch: expected {expected_chip}, got "
            f"{actual_chip or 'unknown'}"
        )

    selected.update(node)
    selected["identityMatch"] = True
    selected["active"] = True
    job.data["accessPoints"] = access_points
    job.progress(
        f"Connected to {node.get('name', ssid)} {actual_chip} "
        f"({node.get('mode', 'unknown')})",
        percent=95,
    )
    return selected


def disconnect_dashboard_node(job: JobStatus) -> dict[str, Any]:
    """Disconnect only an active uNode AP, leaving other Wi-Fi links alone."""

    active = current_connection()
    if not SSID_PATTERN.fullmatch(active):
        raise RuntimeError("wlan0 is not connected to a uNode access point")

    job.data["state"] = "disconnecting"
    job.progress(f"Disconnecting wlan0 from {active}", percent=35)
    run_nmcli("--wait", "20", "connection", "down", "id", active)
    for access_point in job.data.get("accessPoints", []):
        if isinstance(access_point, dict):
            access_point["active"] = False
    job.progress(f"Disconnected wlan0 from {active}", percent=95)
    return {"ssid": active}


def validate_ssid(ssid: str) -> re.Match[str]:
    """Validate a selected node AP and return its chip-ID match."""

    match = SSID_PATTERN.fullmatch(ssid)
    if not match:
        raise ValueError("Selected SSID is not a uNode access point")
    return match


def connect_node(ssid: str) -> None:
    """Connect ``wlan0`` to a uNode AP using its deterministic credential."""

    match = validate_ssid(ssid)
    if current_connection() == ssid:
        return

    # Prefer an existing connection profile because it may contain deliberate
    # local NetworkManager settings. Fall back to the factory AP credential.
    existing = subprocess.run(
        ["nmcli", "connection", "show", "id", ssid],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if existing.returncode == 0:
        try:
            run_nmcli(
                "--wait",
                "20",
                "connection",
                "up",
                "id",
                ssid,
                "ifname",
                WIFI_INTERFACE,
            )
            return
        except RuntimeError:
            # A saved profile may contain an obsolete credential. Remove only
            # that uNode profile, then recreate it with the deterministic AP
            # credential instead of making the node appear unreachable.
            run_nmcli("connection", "delete", "id", ssid)

    password = "artnode" + match.group(1).upper()
    run_nmcli(
        "--wait",
        "20",
        "device",
        "wifi",
        "connect",
        ssid,
        "password",
        password,
        "ifname",
        WIFI_INTERFACE,
        "name",
        ssid,
        "private",
        "yes",
        timeout=30.0,
    )


def get_json(path: str, timeout: float = 2.5) -> dict[str, Any]:
    """Read one public normal/recovery JSON endpoint without authentication."""

    request = urllib.request.Request(BASE_URL + path, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_node(timeout: float = 20.0) -> dict[str, Any]:
    """Detect normal or recovery firmware and return normalized identity."""

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = get_json("/api/status")
            legacy = not bool(status.get("rs485SplitControlSupported", True))
            return {
                "reachable": True,
                "mode": "normal",
                "name": str(status.get("name", "uNode")),
                "chipId": str(status.get("chipId", "")).upper(),
                "firmware": str(status.get("firmware", "unknown")),
                "webAssets": str(status.get("webAssetVersion", "unknown")),
                "webAssetsMatch": bool(status.get("webAssetVersionMatch", False)),
                "inferredProfile": "legacy" if legacy else "normal",
                "ledColorOverrideSupported": bool(
                    status.get("ledColorOverrideSupported", False)
                ),
                "ledOverrideActive": bool(status.get("ledOverrideActive", False)),
                "recoveryMode": False,
            }
        except Exception as error:  # noqa: BLE001 - normal endpoint may not exist in recovery.
            last_error = error

        try:
            status = get_json("/api/recovery/status")
            return {
                "reachable": True,
                "mode": "recovery",
                "name": "uNode Recovery",
                "chipId": str(status.get("chipId", "")).upper(),
                "firmware": str(status.get("firmware", "unknown")),
                "webAssets": "unavailable",
                "webAssetsMatch": False,
                "inferredProfile": "normal",
                "ledColorOverrideSupported": False,
                "ledOverrideActive": False,
                "recoveryMode": True,
                "fsMounted": bool(status.get("fsMounted", False)),
            }
        except Exception as error:  # noqa: BLE001 - AP may still be associating.
            last_error = error

        time.sleep(0.5)

    raise RuntimeError(f"uNode API did not become reachable: {last_error!r}")


def restore_connection(name: str) -> None:
    """Restore the Wi-Fi connection active before an inventory scan."""

    active = current_connection()

    if not name or name == "--":
        if active and active != "--":
            run_nmcli("device", "disconnect", WIFI_INTERFACE)
        return

    if active == name:
        return
    run_nmcli("--wait", "20", "connection", "up", "id", name, "ifname", WIFI_INTERFACE)


def inventory(job: JobStatus) -> list[dict[str, Any]]:
    """Scan, briefly query every uNode AP, then restore the prior Wi-Fi link."""

    job.data["state"] = "scanning"
    job.progress("Scanning for uNode access points", percent=5)
    original = current_connection()
    nodes: list[dict[str, Any]] = []

    try:
        if disconnect_unode_for_scan(original):
            job.progress(
                f"Temporarily disconnected {original} for a complete Wi-Fi scan"
            )

        access_points = scan_access_points()
        total = max(1, len(access_points))
        for index, access_point in enumerate(access_points):
            ssid = str(access_point["ssid"])
            job.progress(
                f"Connecting to {ssid} ({index + 1}/{len(access_points)})",
                percent=10 + int(75 * index / total),
            )
            node = dict(access_point)
            try:
                connect_node(ssid)
                node.update(probe_node())
                expected_chip = validate_ssid(ssid).group(1).upper()
                node["identityMatch"] = node.get("chipId") == expected_chip
                job.progress(
                    f"Found {node.get('name')} {node.get('chipId')} "
                    f"(FW {node.get('firmware')}, {node.get('mode')})"
                )
            except Exception as error:  # noqa: BLE001 - retain unreachable AP in inventory.
                node.update(
                    {
                        "reachable": False,
                        "mode": "unreachable",
                        "firmware": "unknown",
                        "error": str(error),
                    }
                )
                job.progress(f"Could not query {ssid}: {error}")
            nodes.append(node)
            job.data["nodes"] = nodes
            job.write()
    finally:
        job.progress(f"Restoring Wi-Fi connection {original or 'none'}", percent=90)
        restore_connection(original)

    return nodes


def wait_for_normal_node(
    ssid: str,
    *,
    firmware: str | None = None,
    web_assets: str | None = None,
    previous_boot_count: int | None = None,
    password: str | None = None,
    timeout: float = 50.0,
) -> dict[str, Any]:
    """Reconnect after OTA and wait for expected normal-mode versions."""

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    next_connect = 0.0
    client = UNodeClient(BASE_URL, password=password)
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_connect:
            try:
                connect_node(ssid)
            except Exception as error:  # noqa: BLE001 - AP may still be restarting.
                last_error = error
            next_connect = now + 4.0

        try:
            client.ensure_authenticated()
            status = client.get_json("/api/status", timeout=2.0)
            if (
                previous_boot_count is not None
                and int(status.get("bootCount", -1)) <= previous_boot_count
            ):
                time.sleep(0.4)
                continue
            if firmware is not None and str(status.get("firmware")) != firmware:
                time.sleep(0.4)
                continue
            if web_assets is not None and str(status.get("webAssetVersion")) != web_assets:
                time.sleep(0.4)
                continue
            return status
        except Exception as error:  # noqa: BLE001 - reboot polling tolerates link loss.
            last_error = error
        time.sleep(0.4)

    raise RuntimeError(f"Updated node did not return in normal mode: {last_error!r}")


def backup_config(client: UNodeClient, chip_id: str, target_version: str) -> tuple[dict[str, Any], Path]:
    """Download and archive the complete configuration before LittleFS OTA."""

    config = client.get_config()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    path = BACKUP_DIR / f"unode-{chip_id}-config-before-{target_version}-{timestamp}.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config, path


def restore_config(config: dict[str, Any]) -> None:
    """Restore configuration after a complete LittleFS image replacement."""

    client = UNodeClient(BASE_URL)
    client.save_config(config)
    restored = client.get_config()
    for key, expected in config.items():
        if restored.get(key) != expected:
            raise RuntimeError(f"Configuration restore mismatch for {key}")


def run_esptool(
    job: JobStatus,
    port: str,
    arguments: list[str],
    *,
    timeout: float = 180.0,
) -> str:
    """Run one bounded esptool command and append its complete output."""

    if not installed_esptool_version():
        raise RuntimeError(
            "esptool is not installed; rerun tools/bootstrap_test_host.sh"
        )

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp8266",
        "--port",
        port,
        "--baud",
        str(FLASH_BAUD),
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        *arguments,
    ]
    job.log_output("$ " + " ".join(command[2:]))
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = "\n".join(
            value
            for value in (
                str(error.stdout or ""),
                str(error.stderr or ""),
            )
            if value
        )
        job.log_output(output[-100_000:])
        raise RuntimeError(
            f"esptool timed out after {timeout:.0f} seconds"
        ) from error

    output = "\n".join(
        value for value in (result.stdout, result.stderr) if value
    ).strip()
    job.log_output(output[-100_000:])
    if result.returncode != 0:
        detail = output.splitlines()[-1] if output else "no diagnostic output"
        raise RuntimeError(
            f"esptool failed with exit code {result.returncode}: {detail}"
        )
    return output


def parse_esp8266_chip_id(output: str) -> str:
    """Extract the six-digit ESP8266 chip identifier from esptool output."""

    chip_match = re.search(r"Chip ID:\s*0x([0-9a-fA-F]+)", output)
    if chip_match:
        return f"{int(chip_match.group(1), 16) & 0xFFFFFF:06X}"

    mac_match = re.search(
        r"MAC:\s*(?:[0-9a-fA-F]{2}:){3}"
        r"([0-9a-fA-F]{2}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})",
        output,
    )
    if mac_match:
        return "".join(mac_match.groups()).upper()
    raise RuntimeError("Could not read ESP8266 chip ID from esptool output")


def parse_flash_size(output: str) -> int:
    """Extract an auto-detected flash capacity in bytes."""

    match = re.search(
        r"(?:Auto-detected|Detected) flash size:\s*([0-9]+(?:\.[0-9]+)?)\s*([KMG])B",
        output,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("Could not read flash capacity from esptool output")
    multiplier = {
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
    }[match.group(2).upper()]
    return int(float(match.group(1)) * multiplier)


def wait_for_factory_ap(chip_id: str, timeout: float = 35.0) -> dict[str, Any]:
    """Wait for the freshly flashed firmware to advertise its factory AP."""

    expected_ssid = f"uNode_{chip_id}"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            for access_point in scan_access_points():
                if access_point["ssid"] == expected_ssid:
                    return access_point
        except Exception as error:  # noqa: BLE001
            # NetworkManager may still be reconnecting after the hard reset.
            last_error = error
        time.sleep(2.0)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(
        f"Flashing succeeded, but factory AP {expected_ssid} was not discovered{detail}"
    )


def perform_initial_flash(job: JobStatus, request: dict[str, Any]) -> dict[str, Any]:
    """Program and verify one ESP8266 through a DTR/RTS USB adapter."""

    version = str(request.get("version", ""))
    profile = str(request.get("profile", ""))
    requested_port = str(request.get("port", ""))
    erase_all = request.get("eraseAll") is True

    version_key(version)
    if profile not in ALLOWED_PROFILES:
        raise ValueError("Hardware profile must be normal, legacy, or gpio_fix")

    artifacts = resolve_release_artifacts(
        version,
        profile=profile,
        artifacts_dir=ARTIFACTS_DIR,
    )
    manifest_path = ARTIFACTS_DIR / f"uNode-{version}-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("flashLayout") != "4M1M":
        raise RuntimeError("Initial flash requires a 4M1M release manifest")
    if artifacts.firmware.stat().st_size > LITTLEFS_ADDRESS:
        raise RuntimeError("Firmware artifact overlaps the LittleFS region")
    if (
        LITTLEFS_ADDRESS + artifacts.littlefs.stat().st_size
        > EXPECTED_FLASH_BYTES
    ):
        raise RuntimeError("LittleFS artifact exceeds the 4MB flash layout")
    programmer = resolve_serial_programmer(requested_port)
    port = str(programmer["stablePath"])
    job.data["state"] = "flashing"
    job.progress(
        f"Opening {programmer['description']} on {port}",
        percent=5,
    )

    job.progress("Reading ESP8266 chip identity", percent=10)
    identity_output = run_esptool(job, port, ["chip-id"], timeout=45.0)
    chip_id = parse_esp8266_chip_id(identity_output)

    job.progress(f"Reading flash capacity from uNode {chip_id}", percent=18)
    flash_output = run_esptool(job, port, ["flash-id"], timeout=45.0)
    flash_bytes = parse_flash_size(flash_output)
    if flash_bytes != EXPECTED_FLASH_BYTES:
        raise RuntimeError(
            "Unsupported ESP8266 flash capacity: "
            f"{flash_bytes // (1024 * 1024)}MB detected, 4MB required"
        )

    if erase_all:
        job.progress("Erasing complete 4MB flash", percent=25)
        run_esptool(job, port, ["erase-flash"], timeout=120.0)

    job.progress(
        f"Flashing uNode {version} ({profile}) firmware and LittleFS",
        percent=35,
    )
    write_output = run_esptool(
        job,
        port,
        [
            "write-flash",
            "--flash-size",
            "detect",
            f"0x{FIRMWARE_ADDRESS:06X}",
            str(artifacts.firmware),
            f"0x{LITTLEFS_ADDRESS:06X}",
            str(artifacts.littlefs),
        ],
        timeout=240.0,
    )
    verified_blocks = write_output.lower().count("hash of data verified")
    if verified_blocks < 2:
        raise RuntimeError(
            "esptool completed without verifying both firmware and LittleFS"
        )

    job.progress(
        f"Serial flash verified; waiting for factory AP uNode_{chip_id}",
        percent=85,
    )
    access_point = wait_for_factory_ap(chip_id)
    job.progress(
        f"Factory AP uNode_{chip_id} is online at {access_point['signal']}% signal",
        percent=95,
    )
    return {
        "chipId": chip_id,
        "ssid": f"uNode_{chip_id}",
        "version": version,
        "profile": profile,
        "port": port,
        "baud": FLASH_BAUD,
        "flashBytes": flash_bytes,
        "firmwareAddress": FIRMWARE_ADDRESS,
        "littleFsAddress": LITTLEFS_ADDRESS,
        "firmwareSha256": artifacts.firmware_sha256,
        "littleFsSha256": artifacts.littlefs_sha256,
        "verifiedBlocks": verified_blocks,
        "eraseAll": erase_all,
        "accessPoint": access_point,
    }


def normalize_rgb_color(value: Any, label: str) -> str:
    """Validate one dashboard color and normalize it to uppercase #RRGGBB."""

    color = str(value or "")
    if not RGB_COLOR_PATTERN.fullmatch(color):
        raise ValueError(f"{label} must use #RRGGBB format")
    return color.upper()


def normalize_led_brightness(value: Any) -> int:
    """Validate one dashboard LED brightness percentage."""

    if isinstance(value, bool):
        raise ValueError("LED brightness must be an integer from 1 to 100")
    try:
        brightness = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("LED brightness must be an integer from 1 to 100") from error
    if brightness < 1 or brightness > 100:
        raise ValueError("LED brightness must be an integer from 1 to 100")
    return brightness


def perform_led_control(job: JobStatus, request: dict[str, Any]) -> dict[str, Any]:
    """Apply or release volatile WS2812 colors on one selected node."""

    action = str(request.get("action", ""))
    ssid = str(request.get("ssid", ""))
    password = str(request.get("password", "")) or None
    validate_ssid(ssid)

    network_color = ""
    activity_color = ""
    if action == "led-set":
        network_color = normalize_rgb_color(
            request.get("network"),
            "Network LED color",
        )
        activity_color = normalize_rgb_color(
            request.get("activity"),
            "Activity LED color",
        )
        brightness = normalize_led_brightness(request.get("brightness"))
    elif action != "led-release":
        raise ValueError("LED action must be led-set or led-release")

    original = current_connection()
    job.data["state"] = "controlling"

    try:
        job.progress(f"Connecting to selected node {ssid}", percent=10)
        connect_node(ssid)
        node = probe_node()
        expected_chip = validate_ssid(ssid).group(1).upper()
        if node.get("chipId") != expected_chip:
            raise RuntimeError(
                f"Node identity mismatch: SSID {expected_chip}, API {node.get('chipId')}"
            )
        if node.get("recoveryMode"):
            raise RuntimeError("Direct LED control is unavailable in Recovery Mode")
        if not node.get("ledColorOverrideSupported"):
            if node.get("inferredProfile") == "legacy":
                raise RuntimeError("Direct RGB LED control is unavailable on Legacy hardware")
            raise RuntimeError(
                "Direct RGB LED control requires firmware 0.23.25 or newer"
            )

        client = UNodeClient(BASE_URL, password=password)
        client.ensure_authenticated()
        if action == "led-set":
            status, body = client.post_json(
                "/api/brightness",
                {"brightness": brightness},
            )
            if status != 200:
                raise RuntimeError(
                    f"LED brightness API failed with HTTP {status}: "
                    + body.decode(errors="replace")
                )

        endpoint = "/api/leds" if action == "led-set" else "/api/leds/release"
        payload = (
            {"network": network_color, "activity": activity_color}
            if action == "led-set"
            else None
        )
        status, body = client.post_json(endpoint, payload)
        if status != 200:
            raise RuntimeError(
                f"LED API failed with HTTP {status}: "
                + body.decode(errors="replace")
            )
        response = json.loads(body.decode("utf-8"))
        fallback_brightness = brightness if action == "led-set" else 50

        for inventoried_node in job.data.get("nodes", []):
            if inventoried_node.get("ssid") == ssid:
                inventoried_node["ledOverrideActive"] = bool(
                    response.get("overrideActive", False)
                )
                inventoried_node["ledBrightness"] = int(
                    response.get("brightness", fallback_brightness)
                )

        message = (
            f"Applied LED colors to uNode {expected_chip}"
            if action == "led-set"
            else f"Released LED override on uNode {expected_chip}"
        )
        job.progress(message, percent=85)
        return {
            "ssid": ssid,
            "chipId": expected_chip,
            "action": action,
            "leds": response,
        }
    finally:
        job.progress(f"Restoring Wi-Fi connection {original or 'none'}", percent=90)
        restore_connection(original)


def perform_update(job: JobStatus, request: dict[str, Any]) -> dict[str, Any]:
    """Connect to one selected AP and apply verified release artifacts."""

    ssid = str(request.get("ssid", ""))
    version = str(request.get("version", ""))
    profile = str(request.get("profile", ""))
    components = str(request.get("components", ""))
    password = str(request.get("password", "")) or None

    validate_ssid(ssid)
    version_key(version)
    if profile not in ALLOWED_PROFILES:
        raise ValueError("Hardware profile must be normal, legacy, or gpio_fix")
    if components not in ALLOWED_COMPONENTS:
        raise ValueError("Update components must be firmware, littlefs, or both")

    artifacts = resolve_release_artifacts(
        version,
        profile=profile,
        artifacts_dir=ARTIFACTS_DIR,
    )
    job.data["state"] = "updating"
    job.progress(f"Connecting to selected node {ssid}", percent=5)
    connect_node(ssid)
    node = probe_node()
    expected_chip = validate_ssid(ssid).group(1).upper()
    if node.get("chipId") != expected_chip:
        raise RuntimeError(
            f"Node identity mismatch: SSID {expected_chip}, API {node.get('chipId')}"
        )

    job.progress(
        f"Verified {node.get('name')} {node.get('chipId')} "
        f"running {node.get('firmware')} in {node.get('mode')} mode",
        percent=10,
    )

    config: dict[str, Any] | None = None
    backup_path: Path | None = None
    recovery_mode = bool(node.get("recoveryMode"))

    if not recovery_mode:
        client = UNodeClient(BASE_URL, password=password)
        client.ensure_authenticated()
        current_status = client.get_json("/api/status")
        if components in {"littlefs", "both"}:
            config, backup_path = backup_config(client, expected_chip, version)
            job.progress(f"Configuration archived as {backup_path.name}", percent=15)

        if components in {"firmware", "both"}:
            previous_boot_count = int(current_status["bootCount"])
            job.progress(f"Uploading firmware {artifacts.firmware.name}", percent=25)
            response = upload_file(
                BASE_URL,
                "/api/update/firmware",
                artifacts.firmware,
                token=client.token,
            )
            if response.status != 200:
                raise RuntimeError(
                    f"Firmware upload failed with HTTP {response.status}: "
                    + response.body.decode(errors="replace")
                )
            current_status = wait_for_normal_node(
                ssid,
                firmware=version,
                previous_boot_count=previous_boot_count,
                password=password,
            )
            job.progress("Firmware restarted successfully", percent=50)
            client = UNodeClient(BASE_URL, password=password)
            client.ensure_authenticated()

        if components in {"littlefs", "both"}:
            previous_boot_count = int(current_status["bootCount"])
            job.progress(f"Uploading LittleFS {artifacts.littlefs.name}", percent=60)
            response = upload_file(
                BASE_URL,
                "/api/update/fs",
                artifacts.littlefs,
                token=client.token,
                timeout=120.0,
            )
            if response.status != 200:
                raise RuntimeError(
                    f"LittleFS upload failed with HTTP {response.status}: "
                    + response.body.decode(errors="replace")
                )
            current_status = wait_for_normal_node(
                ssid,
                web_assets=version,
                previous_boot_count=previous_boot_count,
                password=password,
            )
            if config is not None:
                job.progress("Restoring archived configuration", percent=85)
                restore_config(config)
    else:
        # Recovery exposes no configuration-download API. Installing LittleFS
        # therefore intentionally restores the release image defaults. Do it
        # before firmware so the following reboot exposes the normal API.
        if components in {"littlefs", "both"}:
            job.progress(
                "Recovery mode: uploading LittleFS; existing configuration cannot be preserved",
                percent=25,
            )
            response = upload_file(
                BASE_URL,
                "/api/update/fs",
                artifacts.littlefs,
                timeout=120.0,
            )
            if response.status != 200:
                raise RuntimeError(
                    f"Recovery LittleFS upload failed with HTTP {response.status}: "
                    + response.body.decode(errors="replace")
                )
            current_status = wait_for_normal_node(
                ssid,
                web_assets=version,
                password=password,
            )
            job.progress("LittleFS recovered and normal mode returned", percent=60)

        if components in {"firmware", "both"}:
            previous_boot_count = (
                int(current_status["bootCount"])
                if components == "both"
                else None
            )
            job.progress(f"Uploading firmware {artifacts.firmware.name}", percent=70)
            # After a recovery LittleFS upload the node is in normal mode with
            # release defaults; firmware-only recovery remains unauthenticated.
            response = upload_file(
                BASE_URL,
                "/api/update/firmware",
                artifacts.firmware,
                timeout=90.0,
            )
            if response.status != 200:
                raise RuntimeError(
                    f"Recovery firmware upload failed with HTTP {response.status}: "
                    + response.body.decode(errors="replace")
                )
            wait_for_normal_node(
                ssid,
                firmware=version,
                previous_boot_count=previous_boot_count,
                password=password,
            )

    final = probe_node()
    job.progress(
        f"Update verified: firmware {final.get('firmware')}, "
        f"web assets {final.get('webAssets')}",
        percent=95,
    )
    return {
        "ssid": ssid,
        "chipId": expected_chip,
        "version": version,
        "profile": profile,
        "components": components,
        "backup": str(backup_path) if backup_path else "",
        "recoveryUpdate": recovery_mode,
        "node": final,
    }


def decode_request(encoded: str) -> dict[str, Any]:
    """Decode one URL-safe base64 JSON request from the Node-RED flow."""

    if not encoded or len(encoded) > 4096:
        raise ValueError("Updater request is missing or too large")
    padding = "=" * (-len(encoded) % 4)
    payload = base64.urlsafe_b64decode(encoded + padding)
    request = json.loads(payload.decode("utf-8"))
    if not isinstance(request, dict):
        raise ValueError("Updater request must be a JSON object")
    return request


def fixture_is_busy() -> bool:
    """Report whether a regression, soak, or updater job owns the fixture."""

    if fcntl is None:
        return False

    TEST_JOB_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TEST_JOB_LOCK_FILE.open("a+", encoding="utf-8") as fixture_lock:
        try:
            fcntl.flock(fixture_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fixture_lock, fcntl.LOCK_UN)
    return False


def idle_status() -> dict[str, Any]:
    """Return persisted state or a fresh idle response."""

    fixture_busy = fixture_is_busy()
    if STATUS_FILE.is_file():
        try:
            status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(status, dict):
                status["releases"] = available_releases()
                status["serialProgrammers"] = serial_programmers()
                status["esptoolVersion"] = installed_esptool_version()
                status["fixtureBusy"] = fixture_busy
                status.setdefault("accessPoints", [])
                if (
                    not fixture_busy
                    and not status.get("running")
                    and status.get("message")
                    == "The uNode test fixture is busy with a regression or soak job"
                ):
                    status.update(
                        {
                            "state": "idle",
                            "message": "Ready to scan for uNode access points",
                            "progress": 0,
                        }
                    )
                return status
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "running": False,
        "state": "idle",
        "message": "Ready to scan for uNode access points",
        "startedAt": "",
        "finishedAt": "",
        "nodes": [],
        "accessPoints": [],
        "releases": available_releases(),
        "serialProgrammers": serial_programmers(),
        "esptoolVersion": installed_esptool_version(),
        "progress": 0,
        "fixtureBusy": fixture_busy,
    }


def run_request(encoded: str) -> int:
    """Execute one locked scan or update request."""

    if fcntl is None:
        raise RuntimeError("uNode updater jobs require Linux file locking")

    request = decode_request(encoded)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_JOB_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock, TEST_JOB_LOCK_FILE.open(
        "w", encoding="utf-8"
    ) as fixture_lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another uNode updater job is already running")

        try:
            fcntl.flock(fixture_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            job = JobStatus(request)
            job.finish(
                "error",
                "The uNode test fixture is busy with a regression or soak job",
            )
            return 75

        job = JobStatus(request)
        try:
            action = request.get("action")
            if action == "scan":
                nodes = inventory(job)
                message = (
                    f"Scan complete: {len(nodes)} uNode access point(s) found"
                )
                job.finish("ready", message, nodes=nodes)
            elif action == "network-scan":
                access_points = scan_for_dashboard_connection(job)
                message = (
                    f"Wi-Fi scan complete: {len(access_points)} uNode "
                    "access point(s) found"
                )
                job.finish("ready", message, accessPoints=access_points)
            elif action == "network-connect":
                result = connect_dashboard_node(job, request)
                job.finish(
                    "ready",
                    f"Connected wlan0 to {result['ssid']}",
                    result=result,
                    accessPoints=job.data["accessPoints"],
                )
            elif action == "network-disconnect":
                result = disconnect_dashboard_node(job)
                job.finish(
                    "ready",
                    f"Disconnected wlan0 from {result['ssid']}",
                    result=result,
                    accessPoints=job.data["accessPoints"],
                )
            elif action == "update":
                result = perform_update(job, request)
                job.finish(
                    "updated",
                    f"uNode {result['chipId']} updated to {result['version']}",
                    result=result,
                )
            elif action == "initial-flash":
                result = perform_initial_flash(job, request)
                job.finish(
                    "flashed",
                    f"uNode {result['chipId']} initially flashed to {result['version']}",
                    result=result,
                )
            elif action in {"led-set", "led-release"}:
                result = perform_led_control(job, request)
                job.finish(
                    "ready",
                    (
                        f"LED colors applied to uNode {result['chipId']}"
                        if action == "led-set"
                        else f"LED override released on uNode {result['chipId']}"
                    ),
                    result=result,
                )
            else:
                raise ValueError(
                    "Updater action must be scan, network-scan, network-connect, "
                    "network-disconnect, update, initial-flash, led-set, or "
                    "led-release"
                )
        except Exception as error:  # noqa: BLE001 - surface complete failure in dashboard.
            job.finish("error", str(error))
            return 1
    return 0


def main() -> int:
    """Command-line entry point used by Node-RED and unit tests."""

    if len(sys.argv) < 2:
        raise SystemExit("Usage: node_updater.py status | releases | request BASE64JSON")

    command = sys.argv[1]
    if command == "status":
        print(json.dumps(idle_status()))
        return 0
    if command == "releases":
        print(json.dumps(available_releases()))
        return 0
    if command == "request" and len(sys.argv) == 3:
        return run_request(sys.argv[2])
    raise SystemExit("Usage: node_updater.py status | releases | request BASE64JSON")


if __name__ == "__main__":
    raise SystemExit(main())
