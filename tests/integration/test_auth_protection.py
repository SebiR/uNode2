from __future__ import annotations

import json

from helpers import step
from unode_client import UNodeClient


def _set_password(client: UNodeClient, password: str) -> str:
    status, body = client.post_json(
        "/api/auth/password",
        {"password": password},
    )
    assert status == 200, body.decode(errors="replace")

    response = json.loads(body.decode("utf-8"))
    token = response.get("token", "")
    client.token = token
    return token


def _login(client: UNodeClient, password: str) -> str:
    status, body = client.post_json(
        "/api/auth/login",
        {"password": password},
    )
    assert status == 200, body.decode(errors="replace")

    token = json.loads(body.decode("utf-8")).get("token", "")
    client.token = token
    assert token
    return token


def test_api_write_endpoints_require_auth_when_password_is_enabled(
    unode_client: UNodeClient,
) -> None:
    step("Reading initial authentication state")
    initial = unode_client.get_json("/api/auth/status")
    initially_enabled = bool(initial.get("enabled", False))
    original_password = unode_client.password if initially_enabled else ""

    if initially_enabled and not original_password:
        raise AssertionError(
            "uNode already has a password; set UNODE_PASSWORD so the test can "
            "restore it afterwards"
        )

    temporary_password = "uNode-regression-auth"

    try:
        step("Enabling a temporary password for API protection checks")
        token = _set_password(unode_client, temporary_password)
        assert token

        anonymous = UNodeClient(unode_client.base_url)

        step("Checking that read-only status endpoints remain readable")
        status = anonymous.get_json("/api/status")
        assert status["firmware"]
        auth_status = anonymous.get_json("/api/auth/status")
        assert auth_status["enabled"] is True
        assert auth_status["authenticated"] is False

        step("Checking that wrong passwords are rejected")
        login_status, _body = anonymous.post_json(
            "/api/auth/login",
            {"password": "definitely-wrong"},
        )
        assert login_status == 403

        protected_requests = [
            ("/api/config", {}),
            ("/api/artnet/poll", None),
            ("/api/dmx/release", None),
            ("/api/failsafe/record", None),
            ("/api/auth/password", {"password": "should-not-apply"}),
        ]

        for path, payload in protected_requests:
            step(f"Checking unauthenticated write protection on {path}")
            write_status, body = anonymous.post_json(path, payload)
            assert write_status == 403, body.decode(errors="replace")

        step("Checking that config download requires authentication")
        download_status, _content_type, body = anonymous._request(
            "GET",
            "/api/config/download",
        )
        assert download_status == 403, body.decode(errors="replace")

        step("Logging in with the temporary password")
        _login(anonymous, temporary_password)
        # Login creates a fresh volatile session token on the node. Keep the
        # main client in sync so cleanup cannot be locked out by its old token.
        unode_client.token = anonymous.token

        step("Checking that an authenticated mutating API request is accepted")
        poll_status, body = anonymous.post_json("/api/artnet/poll")
        assert poll_status == 202, body.decode(errors="replace")

        step("Checking that authenticated config download is accepted")
        download_status, content_type, body = anonymous._request(
            "GET",
            "/api/config/download",
        )
        assert download_status == 200, body.decode(errors="replace")
        assert "application/json" in content_type
        assert json.loads(body.decode("utf-8"))

        step("Checking that logout invalidates the current token")
        logout_status, body = anonymous.post_json("/api/auth/logout")
        assert logout_status == 200, body.decode(errors="replace")
        auth_status = anonymous.get_json("/api/auth/status")
        assert auth_status["enabled"] is True
        assert auth_status["authenticated"] is False

        poll_status, body = anonymous.post_json("/api/artnet/poll")
        assert poll_status == 403, body.decode(errors="replace")

        # Re-login for reliable cleanup.
        _login(unode_client, temporary_password)

    finally:
        step("Restoring original authentication configuration")
        restore_status, restore_body = unode_client.post_json(
            "/api/auth/password",
            {"password": original_password or ""},
        )
        if restore_status == 403:
            # The token may have been invalidated by a successful login check.
            _login(unode_client, temporary_password)
            restore_status, restore_body = unode_client.post_json(
                "/api/auth/password",
                {"password": original_password or ""},
            )

        assert restore_status == 200, restore_body.decode(errors="replace")
        response = json.loads(restore_body.decode("utf-8"))
        unode_client.token = response.get("token", "")
