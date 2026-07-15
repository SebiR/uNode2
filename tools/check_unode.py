#!/usr/bin/env python3
"""Verify that a normal-mode uNode is reachable before hardware tests start."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def _read_status(base_url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/status",
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("status response is not a JSON object")
    if not value.get("firmware") or not value.get("chipId"):
        raise RuntimeError("response does not identify a uNode")
    if value.get("recoveryMode") is True:
        raise RuntimeError("node is in Recovery Mode")
    return value


def wait_for_unode(
    base_url: str,
    *,
    attempts: int = 3,
    timeout: float = 2.0,
    interval: float = 0.5,
) -> dict[str, Any]:
    """Return status after a bounded reachability check or raise RuntimeError."""

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _read_status(base_url, timeout)
        except (
            OSError,
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            RuntimeError,
        ) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(interval)

    raise RuntimeError(
        f"no normal-mode uNode answered at {base_url.rstrip('/')} "
        f"after {attempts} attempts ({last_error})"
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://2.0.0.1")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    if args.attempts < 1 or args.timeout <= 0 or args.interval < 0:
        parser.error("attempts and timeout must be positive; interval cannot be negative")

    try:
        status = wait_for_unode(
            args.base_url,
            attempts=args.attempts,
            timeout=args.timeout,
            interval=args.interval,
        )
    except RuntimeError as error:
        print(f"uNode preflight failed: {error}")
        print("Connect the test host to the node network, then start the test again.")
        return 3

    print(
        "uNode preflight OK: "
        f"{status.get('name', 'uNode')} {status['chipId']} "
        f"(FW {status['firmware']}, {status.get('ip', args.base_url)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
