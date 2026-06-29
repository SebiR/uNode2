"""Discover uNode devices with ArtPoll on available IPv4 interfaces."""

from __future__ import annotations

import argparse
import ipaddress
import json
import platform
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = PROJECT_ROOT / "tests"
sys.path.insert(0, str(TESTS_DIR))

from artnet_packets import ARTNET_PORT, make_artpoll, parse_artpollreply  # noqa: E402


@dataclass(frozen=True)
class InterfaceTarget:
    local_ip: str
    broadcast_ip: str
    name: str = ""


@dataclass(frozen=True)
class DiscoveredNode:
    ip: str
    short_name: str
    long_name: str
    firmware: str
    local_ip: str
    broadcast_ip: str
    interface: str


def _prefix_to_broadcast(address: str, prefix_length: int) -> str:
    network = ipaddress.IPv4Network(f"{address}/{prefix_length}", strict=False)
    return str(network.broadcast_address)


def _windows_interfaces() -> list[InterfaceTarget]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-NetIPAddress -AddressFamily IPv4 "
            "| Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } "
            "| Select-Object IPAddress,PrefixLength,InterfaceAlias "
            "| ConvertTo-Json -Compress"
        ),
    ]

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return []

    data = json.loads(result.stdout)
    if isinstance(data, dict):
        data = [data]

    targets: list[InterfaceTarget] = []
    for entry in data:
        address = str(entry.get("IPAddress", ""))
        if not address:
            continue
        try:
            broadcast = _prefix_to_broadcast(
                address,
                int(entry.get("PrefixLength", 24)),
            )
        except (ValueError, TypeError):
            continue
        targets.append(
            InterfaceTarget(
                local_ip=address,
                broadcast_ip=broadcast,
                name=str(entry.get("InterfaceAlias", "")),
            )
        )
    return targets


def _hostname_interfaces() -> list[InterfaceTarget]:
    targets: list[InterfaceTarget] = []
    seen: set[str] = set()

    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = info[4][0]
        if address.startswith("127.") or address in seen:
            continue
        seen.add(address)
        # Fallback when the OS-specific path is unavailable. It is intentionally
        # broad but still useful for uNode AP mode and many /24 lab networks.
        octets = address.split(".")
        broadcast = ".".join(octets[:3] + ["255"])
        targets.append(
            InterfaceTarget(
                local_ip=address,
                broadcast_ip=broadcast,
                name="hostname",
            )
        )
    return targets


def _discover_interfaces() -> list[InterfaceTarget]:
    if platform.system().lower() == "windows":
        targets = _windows_interfaces()
    else:
        targets = []

    if not targets:
        targets = _hostname_interfaces()

    unique: dict[tuple[str, str], InterfaceTarget] = {}
    for target in targets:
        if target.broadcast_ip == target.local_ip:
            continue
        unique[(target.local_ip, target.broadcast_ip)] = target

    return list(unique.values())


def _make_node(
    packet: bytes,
    *,
    sender_ip: str,
    target: InterfaceTarget,
) -> DiscoveredNode | None:
    try:
        reply = parse_artpollreply(packet)
    except ValueError:
        return None

    firmware = f"{reply.firmware_version[0]}.{reply.firmware_version[1]}"
    return DiscoveredNode(
        ip=sender_ip,
        short_name=reply.short_name,
        long_name=reply.long_name,
        firmware=firmware,
        local_ip=target.local_ip,
        broadcast_ip=target.broadcast_ip,
        interface=target.name,
    )


def discover(timeout: float) -> list[DiscoveredNode]:
    targets = _discover_interfaces()
    nodes: dict[str, DiscoveredNode] = {}
    sockets: list[tuple[socket.socket, InterfaceTarget]] = []

    try:
        for target in targets:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.05)

            try:
                sock.bind((target.local_ip, ARTNET_PORT))
            except OSError:
                sock.close()
                continue

            sockets.append((sock, target))

            for destination in {
                target.broadcast_ip,
                "255.255.255.255",
                "2.255.255.255",
                "2.0.0.255",
            }:
                try:
                    sock.sendto(make_artpoll(), (destination, ARTNET_PORT))
                except OSError:
                    continue

        deadline = time.time() + timeout
        while time.time() < deadline:
            for sock, target in sockets:
                try:
                    data, sender = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    continue

                node = _make_node(
                    data,
                    sender_ip=sender[0],
                    target=target,
                )
                if node is not None:
                    nodes[node.ip] = node

        return sorted(nodes.values(), key=lambda item: item.ip)
    finally:
        for sock, _target in sockets:
            sock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--first-ip", action="store_true")
    args = parser.parse_args()

    nodes = discover(timeout=args.timeout)

    if args.first_ip:
        if nodes:
            print(nodes[0].ip)
            return 0
        return 1

    if args.json:
        print(json.dumps([asdict(node) for node in nodes], indent=2))
    else:
        for node in nodes:
            label = node.short_name or node.long_name or "uNode"
            print(
                f"{node.ip}  {label}  FW {node.firmware}  "
                f"via {node.local_ip}->{node.broadcast_ip}"
            )

    return 0 if nodes else 1


if __name__ == "__main__":
    raise SystemExit(main())
