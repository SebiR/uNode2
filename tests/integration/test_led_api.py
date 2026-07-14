from __future__ import annotations

import json

import pytest

from helpers import step
from unode_client import UNodeClient


def _decode(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def test_led_api_applies_and_releases_volatile_rgb_override(
    unode_client: UNodeClient,
) -> None:
    initial_status = unode_client.get_json("/api/status")
    if not initial_status.get("ledColorOverrideSupported", False):
        pytest.skip("Direct RGB LED override is unavailable on Legacy hardware")

    step("Releasing any LED override left by an interrupted earlier test")
    status, body = unode_client.post_json("/api/leds/release")
    assert status == 200, body.decode(errors="replace")

    try:
        step("Applying direct LED colors using hex and RGB object forms")
        status, body = unode_client.post_json(
            "/api/leds",
            {
                "network": "#123456",
                "activity": {"r": 171, "g": 205, "b": 239},
            },
        )
        assert status == 200, body.decode(errors="replace")

        response = _decode(body)
        assert response["overrideActive"] is True
        assert response["network"] == {
            "r": 18,
            "g": 52,
            "b": 86,
            "hex": "#123456",
        }
        assert response["activity"] == {
            "r": 171,
            "g": 205,
            "b": 239,
            "hex": "#ABCDEF",
        }

        step("Checking that read-only LED and node status expose the override")
        led_state = unode_client.get_json("/api/leds")
        assert led_state["overrideActive"] is True
        assert led_state["network"]["hex"] == "#123456"
        assert led_state["activity"]["hex"] == "#ABCDEF"

        node_status = unode_client.get_json("/api/status")
        assert node_status["ledOverrideActive"] is True

        step("Rejecting malformed colors without replacing the active override")
        status, _body = unode_client.post_json(
            "/api/leds",
            {
                "network": "#not-rgb",
                "activity": {"r": 0, "g": 0, "b": 256},
            },
        )
        assert status == 400
        assert unode_client.get_json("/api/leds")["overrideActive"] is True
    finally:
        step("Releasing direct colors back to the normal status LED logic")
        status, body = unode_client.post_json("/api/leds/release")
        assert status == 200, body.decode(errors="replace")

    released = _decode(body)
    assert released["overrideActive"] is False
    assert unode_client.get_json("/api/status")["ledOverrideActive"] is False
