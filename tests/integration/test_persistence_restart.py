from __future__ import annotations

from helpers import (
    configured_port_address,
    request_artpoll_reply,
    step,
    wait_for_node_restart,
    wait_for_status,
)
from unode_client import UNodeClient


def _different_int(value: int, *, modulo: int, avoid_zero: bool = False) -> int:
    next_value = (int(value) + 1) % modulo
    if avoid_zero and next_value == 0:
        next_value = 1
    return next_value


def _different_brightness(value: int) -> int:
    return 73 if int(value) != 73 else 42


def test_runtime_and_hardware_settings_persist_after_api_restart(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["shortName"] = "PERSIST_uNode"
    config["longName"] = "uNode Persistence Regression"
    config["direction"] = 0  # Art-Net -> DMX, easy to verify via SwOut.
    config["net"] = _different_int(config.get("net", 0), modulo=128)
    config["subnetId"] = _different_int(config.get("subnetId", 0), modulo=16)
    config["universe"] = _different_int(
        config.get("universe", 1),
        modulo=16,
        avoid_zero=True,
    )
    config["failsafeMode"] = _different_int(
        config.get("failsafeMode", 0),
        modulo=4,
    )
    config["mergeMode"] = _different_int(
        config.get("mergeMode", 0),
        modulo=2,
    )
    config["terminationMode"] = _different_int(
        config.get("terminationMode", 2),
        modulo=3,
    )
    config["legacyArtPollReply"] = not bool(config.get("legacyArtPollReply", False))
    config["ledBrightness"] = _different_brightness(config.get("ledBrightness", 50))
    # Keep boot-time auto-switching disabled during this restart-focused test so
    # an unrelated physical DMX signal cannot change the expected direction.
    config["busGuardMode"] = 0

    port_address = configured_port_address(config)
    before_save = unode_client.get_json("/api/status")
    initial_boot_count = int(before_save["bootCount"])

    step(
        "Saving persistent runtime/hardware config before restart: "
        f"name={config['shortName']}, portAddress={port_address}, "
        f"failsafe={config['failsafeMode']}, merge={config['mergeMode']}, "
        f"termination={config['terminationMode']}, "
        f"legacy={config['legacyArtPollReply']}"
    )
    response = unode_client.save_config(config)
    assert "restartRequired" in response

    step(f"Restarting node via REST API from bootCount={initial_boot_count}")
    restart_status, body = unode_client.post_json("/api/restart")
    assert restart_status == 200, body.decode(errors="replace")

    restarted = wait_for_node_restart(
        unode_client,
        previous_boot_count=initial_boot_count,
    )
    step(
        "Node restarted: "
        f"bootCount={restarted['bootCount']}, direction={restarted['direction']}, "
        f"portAddress={restarted['universe']}"
    )

    step("Reading persisted config after restart")
    persisted = unode_client.get_config()
    for key in (
        "shortName",
        "longName",
        "direction",
        "net",
        "subnetId",
        "universe",
        "failsafeMode",
        "mergeMode",
        "terminationMode",
        "legacyArtPollReply",
        "ledBrightness",
        "busGuardMode",
    ):
        assert persisted[key] == config[key], f"{key} did not persist"

    step("Checking /api/status after restart")
    status = wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == config["direction"]
        and int(data["universe"]) == port_address
        and int(data["failsafeMode"]) == config["failsafeMode"]
        and int(data["mergeMode"]) == config["mergeMode"]
        and int(data["terminationMode"]) == config["terminationMode"]
        and int(data["busGuardMode"]) == config["busGuardMode"]
        and data["name"] == config["shortName"],
    )
    assert int(status["bootCount"]) > initial_boot_count

    step("Checking ArtPollReply after restart")
    reply = request_artpoll_reply(unode_ip)
    assert reply.short_name == config["shortName"]
    assert reply.long_name == config["longName"]
    assert reply.net == config["net"]
    assert reply.subnet == config["subnetId"]
    assert reply.sw_out[0] == config["universe"]
