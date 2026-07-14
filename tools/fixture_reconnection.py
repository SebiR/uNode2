"""Run the uNode reconnect test through a temporary Raspberry Pi hotspot.

The node is initially reachable through its factory/configured AP. A test-
harness firmware receives volatile credentials, while NetworkManager changes
the Pi Wi-Fi interface into an isolated hotspot. After pytest finishes, the
node is restarted (discarding the RAM-only credentials) and the Pi restores
its previous Wi-Fi connection. Ethernet/Node-RED remains unaffected.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = PROJECT_ROOT / "tests"
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from discover_unode import discover  # noqa: E402
from unode_client import UNodeClient  # noqa: E402


DEFAULT_SSID = "uNode-Fixture"
DEFAULT_PASSWORD = "uNodeFixture24"
DEFAULT_CONNECTION = "uNode-Fixture-Hotspot"


def _nmcli(*arguments: str, timeout: float = 30.0, check: bool = True) -> str:
    result = subprocess.run(
        ["nmcli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"nmcli {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def _current_connection(interface: str) -> str:
    value = _nmcli(
        "-g",
        "GENERAL.CONNECTION",
        "device",
        "show",
        interface,
    )
    return "" if value in {"", "--"} else value.splitlines()[0].strip()


def _delete_connection(name: str) -> None:
    _nmcli("connection", "delete", "id", name, check=False)


def _prepare_hotspot_profile(
    interface: str,
    connection: str,
    ssid: str,
    password: str,
) -> None:
    _delete_connection(connection)
    _nmcli(
        "connection",
        "add",
        "type",
        "wifi",
        "ifname",
        interface,
        "con-name",
        connection,
        "autoconnect",
        "no",
        "ssid",
        ssid,
    )
    _nmcli(
        "connection",
        "modify",
        connection,
        "802-11-wireless.mode",
        "ap",
        "802-11-wireless.band",
        "bg",
        "ipv4.method",
        "shared",
        "ipv6.method",
        "disabled",
        "wifi-sec.key-mgmt",
        "wpa-psk",
        "wifi-sec.psk",
        password,
    )


def _find_node(chip_id: str, password: str | None, timeout: float) -> UNodeClient:
    deadline = time.monotonic() + timeout
    last_nodes: list[str] = []
    while time.monotonic() < deadline:
        for node in discover(timeout=1.0):
            last_nodes.append(node.ip)
            candidate = UNodeClient(f"http://{node.ip}", password)
            try:
                candidate.ensure_authenticated()
                status = candidate.get_json("/api/status", timeout=2.0)
            except Exception:  # noqa: BLE001 - radio/DHCP convergence is expected.
                continue
            if str(status.get("chipId", "")).upper() == chip_id.upper():
                return candidate
        time.sleep(0.5)
    raise TimeoutError(
        f"uNode {chip_id} did not appear on fixture hotspot; seen={last_nodes}"
    )


def _restore_connection(interface: str, previous: str, timeout: float = 75.0) -> None:
    if not previous:
        _nmcli("device", "disconnect", interface, check=False)
        return

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "nmcli",
                "--wait",
                "10",
                "connection",
                "up",
                "id",
                previous,
                "ifname",
                interface,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"[fixture] Restored Pi Wi-Fi connection: {previous}")
            return
        time.sleep(2.0)
    raise TimeoutError(f"Could not restore Pi Wi-Fi connection {previous!r}")


def _run_pytest(client: UNodeClient) -> int:
    node_ip = client.base_url.rsplit("/", 1)[-1]
    environment = os.environ.copy()
    environment.update(
        {
            "UNODE_RUN_INTEGRATION": "1",
            "UNODE_RUN_RECONNECTION": "1",
            "UNODE_IP": node_ip,
            "UNODE_BASE_URL": client.base_url,
        }
    )
    if client.password:
        environment["UNODE_PASSWORD"] = client.password
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-s",
            "-vv",
            "tests/integration/test_network_reconnection.py",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://2.0.0.1")
    parser.add_argument("--password", default=os.environ.get("UNODE_PASSWORD", ""))
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--ssid", default=DEFAULT_SSID)
    parser.add_argument("--hotspot-password", default=DEFAULT_PASSWORD)
    parser.add_argument("--connection", default=DEFAULT_CONNECTION)
    args = parser.parse_args()

    password = args.password or None
    initial = UNodeClient(args.base_url, password)
    initial.ensure_authenticated()
    initial_status = initial.get_json("/api/status")

    if initial_status.get("wifiConnected", False):
        print("[fixture] Node already uses Client mode; no hotspot transition needed")
        return _run_pytest(initial)

    diagnostics = initial_status.get("networkDiagnostics", {})
    if not diagnostics.get("testHarnessApiEnabled", False):
        raise RuntimeError(
            "Node is in AP mode but firmware was built without "
            "ENABLE_TEST_HARNESS_API=1"
        )

    chip_id = str(initial_status.get("chipId", ""))
    if not chip_id:
        raise RuntimeError("Node status did not provide a chip ID")

    previous = _current_connection(args.interface)
    fixture_client: UNodeClient | None = None
    result = 1

    print(
        f"[fixture] Preparing temporary hotspot {args.ssid!r}; "
        f"previous Pi connection={previous or 'none'}"
    )
    _prepare_hotspot_profile(
        args.interface,
        args.connection,
        args.ssid,
        args.hotspot_password,
    )

    try:
        status_code, body = initial.post_json(
            "/api/test/network/client",
            {
                "ssid": args.ssid,
                "password": args.hotspot_password,
                "switchDelayMs": 5000,
                "connectTimeoutMs": 60000,
            },
        )
        if status_code != 202:
            raise RuntimeError(
                "Temporary Client request failed with HTTP "
                f"{status_code}: {body.decode(errors='replace')}"
            )

        print("[fixture] Starting Raspberry Pi hotspot")
        _nmcli(
            "--wait",
            "20",
            "connection",
            "up",
            "id",
            args.connection,
            "ifname",
            args.interface,
            timeout=25.0,
        )
        fixture_client = _find_node(chip_id, password, timeout=60.0)
        print(f"[fixture] Node joined temporary network at {fixture_client.base_url}")
        result = _run_pytest(fixture_client)
    finally:
        if fixture_client is not None:
            try:
                print("[fixture] Restarting node to discard volatile credentials")
                fixture_client.post_json("/api/restart", timeout=3.0)
                time.sleep(0.5)
            except Exception as error:  # noqa: BLE001 - cleanup must continue.
                print(f"[fixture] Node restart request warning: {error}", file=sys.stderr)

        _nmcli("connection", "down", "id", args.connection, check=False)
        _delete_connection(args.connection)
        _restore_connection(args.interface, previous)

    return result


if __name__ == "__main__":
    raise SystemExit(main())
