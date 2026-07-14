"""Minimal uNode REST client for integration tests."""

from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class UNodeClient:
    base_url: str
    password: str | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.token = ""
        self.prefer_detailed_status = False

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, str, bytes]:
        body = None
        headers: dict[str, str] = {}

        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.token:
            headers["X-uNode-Auth"] = self.token

        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )

        last_error: Exception | None = None

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return (
                        response.status,
                        response.headers.get("Content-Type", ""),
                        response.read(),
                    )
            except urllib.error.HTTPError as error:
                return (
                    error.code,
                    error.headers.get("Content-Type", ""),
                    error.read(),
                )
            except (
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                ConnectionResetError,
                TimeoutError,
                socket.timeout,
                urllib.error.URLError,
            ) as error:
                last_error = error
                if attempt == 2:
                    break
                time.sleep(0.15 * (attempt + 1))

        if last_error is not None:
            raise last_error

        raise AssertionError(f"{method} {path} failed without response")

    def get_json(self, path: str, *, timeout: float = 5.0) -> dict[str, Any]:
        request_path = path
        if (
            self.prefer_detailed_status
            and path.split("?", 1)[0] == "/api/status"
        ):
            suffix = "?" + path.split("?", 1)[1] if "?" in path else ""
            request_path = "/api/diagnostics" + suffix

        status, _content_type, body = self._request(
            "GET",
            request_path,
            timeout=timeout,
        )
        if request_path.startswith("/api/diagnostics") and status == 404:
            # The embedded Recovery Mode exposes only its compact /api/status.
            request_path = path
            status, _content_type, body = self._request(
                "GET",
                request_path,
                timeout=timeout,
            )
        if status < 200 or status >= 300:
            raise AssertionError(
                f"GET {request_path} failed with HTTP {status}: {body!r}"
            )
        return json.loads(body.decode("utf-8"))

    def post_json(
        self,
        path: str,
        data: Any | None = None,
        *,
        timeout: float = 5.0,
    ) -> tuple[int, bytes]:
        status, _content_type, body = self._request(
            "POST",
            path,
            data=data,
            timeout=timeout,
        )
        return status, body

    def ensure_authenticated(self) -> None:
        auth_status = self.get_json("/api/auth/status")
        if not auth_status.get("enabled", False):
            self.prefer_detailed_status = True
            return
        if auth_status.get("authenticated", False):
            self.prefer_detailed_status = True
            return
        if not self.password:
            raise AssertionError(
                "uNode requires login; set UNODE_PASSWORD for integration tests"
            )

        status, body = self.post_json(
            "/api/auth/login",
            {"password": self.password},
        )
        if status != 200:
            raise AssertionError(f"Login failed with HTTP {status}: {body!r}")

        response = json.loads(body.decode("utf-8"))
        self.token = response.get("token", "")
        if not self.token:
            raise AssertionError("Login response did not contain an auth token")

        self.prefer_detailed_status = True

    def get_config(self) -> dict[str, Any]:
        return self.get_json("/api/config")

    def save_config(self, config: dict[str, Any]) -> dict[str, Any]:
        self.ensure_authenticated()
        status, body = self.post_json("/api/config", config)
        if status != 200:
            raise AssertionError(
                f"Saving config failed with HTTP {status}: {body.decode(errors='replace')}"
            )
        return json.loads(body.decode("utf-8"))
