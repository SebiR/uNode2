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
    status, body = request(args.url, "GET", "/flows")
    if status != 200:
        raise SystemExit(f"Node-RED flow list failed with HTTP {status}")

    flow_list_response = json.loads(body.decode("utf-8"))
    installed_nodes = (
        flow_list_response.get("flows", [])
        if isinstance(flow_list_response, dict)
        else flow_list_response
    )
    installed_tab = next(
        (
            node
            for node in installed_nodes
            if node.get("type") == "tab"
            and node.get("label") == flow.get("label")
        ),
        None,
    )

    if installed_tab is not None:
        flow_id = installed_tab["id"]
        flow["id"] = flow_id
        for node in flow.get("nodes", []):
            node["z"] = flow_id
        for config in flow.get("configs", []):
            config["z"] = flow_id
        method = "PUT"
        path = f"/flow/{flow_id}"
        action = "updated"
    else:
        method = "POST"
        path = "/flow"
        action = "created"

    status, body = request(args.url, method, path, flow)
    if not 200 <= status < 300:
        detail = body.decode("utf-8", errors="replace")
        raise SystemExit(f"Node-RED deployment failed with HTTP {status}: {detail}")

    print(f"uNode dashboard {action}: {args.url.rstrip('/')}/unode/status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
