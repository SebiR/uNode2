from __future__ import annotations

import json
from types import SimpleNamespace

from tools import discover_unode


def test_linux_interfaces_include_ethernet_and_wifi(monkeypatch) -> None:
    ip_output = [
        {
            "ifname": "lo",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "127.0.0.1",
                    "prefixlen": 8,
                    "scope": "host",
                }
            ],
        },
        {
            "ifname": "eth0",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "192.168.1.244",
                    "prefixlen": 24,
                    "broadcast": "192.168.1.255",
                    "scope": "global",
                }
            ],
        },
        {
            "ifname": "wlan0",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "2.0.0.101",
                    "prefixlen": 24,
                    "broadcast": "2.0.0.255",
                    "scope": "global",
                }
            ],
        },
    ]

    monkeypatch.setattr(
        discover_unode.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(ip_output),
        ),
    )

    assert discover_unode._linux_interfaces() == [
        discover_unode.InterfaceTarget(
            local_ip="192.168.1.244",
            broadcast_ip="192.168.1.255",
            name="eth0",
        ),
        discover_unode.InterfaceTarget(
            local_ip="2.0.0.101",
            broadcast_ip="2.0.0.255",
            name="wlan0",
        ),
    ]


def test_linux_interface_broadcast_is_derived_when_missing(monkeypatch) -> None:
    ip_output = [
        {
            "ifname": "wlan0",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "2.0.0.101",
                    "prefixlen": 24,
                    "scope": "global",
                }
            ],
        }
    ]

    monkeypatch.setattr(
        discover_unode.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(ip_output),
        ),
    )

    assert discover_unode._linux_interfaces()[0].broadcast_ip == "2.0.0.255"
