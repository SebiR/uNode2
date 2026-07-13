"""Create or update the read-only uNode Node-RED dashboard flow."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_FLOW = Path(__file__).with_name("unode-dashboard-flow.json")


def request(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
) -> tuple[int, bytes]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Node-RED-API-Version": "v2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:1880")
    parser.add_argument("--flow", type=Path, default=DEFAULT_FLOW)
    args = parser.parse_args()

    flow = json.loads(args.flow.read_text(encoding="utf-8"))
    flow_id = flow["id"]
    status, _body = request(args.url, "GET", f"/flow/{flow_id}")

    if status == 200:
        method = "PUT"
        path = f"/flow/{flow_id}"
        action = "updated"
    elif status == 404:
        method = "POST"
        path = "/flow"
        action = "created"
    else:
        raise SystemExit(f"Node-RED flow lookup failed with HTTP {status}")

    status, body = request(args.url, method, path, flow)
    if not 200 <= status < 300:
        detail = body.decode("utf-8", errors="replace")
        raise SystemExit(f"Node-RED deployment failed with HTTP {status}: {detail}")

    print(f"uNode dashboard {action}: {args.url.rstrip('/')}/unode/status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
