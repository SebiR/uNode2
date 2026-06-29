from __future__ import annotations

from artnet_packets import make_artdmx, make_artsync
from helpers import configured_port_address, send_artnet_packet, step, wait_for_status
from unode_client import UNodeClient


def _configure_artnet_output_for_artsync(
    unode_client: UNodeClient,
    preserved_config: dict,
) -> tuple[dict, int]:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX
    config["liveProtocol"] = 0  # Art-Net live data

    reset_config = config.copy()
    reset_config["direction"] = 1  # DMX -> Art-Net, clears ArtSync/sequence state.

    step("Resetting Art-Net runtime state before ArtSync test")
    unode_client.save_config(reset_config)
    reset_universe = configured_port_address(reset_config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 1
        and int(data["universe"]) == reset_universe,
    )

    step("Switching node to Art-Net -> DMX for ArtSync test")
    unode_client.save_config(config)
    universe = configured_port_address(config)
    wait_for_status(
        unode_client,
        lambda data: int(data["direction"]) == 0
        and int(data["universe"]) == universe
        and data["artSyncActive"] is False
        and data["artSyncPending"] is False,
    )

    return config, universe


def test_artsync_buffers_artdmx_until_sync_packet(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_artnet_output_for_artsync(
        unode_client,
        preserved_config,
    )
    before = unode_client.get_json("/api/status")
    before_syncs = int(before["artSyncs"])
    before_packets = int(before["artnetPackets"])

    step("Sending ArtSync to enable synchronous ArtDmx output mode")
    send_artnet_packet(unode_ip, make_artsync())

    status = wait_for_status(
        unode_client,
        lambda data: int(data["artSyncs"]) > before_syncs
        and data["artSyncActive"] is True
        and data["artSyncPending"] is False,
    )

    step(
        "ArtSync active: "
        f"syncs={status['artSyncs']}, pending={status['artSyncPending']}"
    )

    step(f"Sending ArtDmx to Port-Address {universe}; output should stay pending")
    send_artnet_packet(
        unode_ip,
        make_artdmx(
            universe,
            [11, 22, 33, 44],
            sequence=0,
        ),
    )

    status = wait_for_status(
        unode_client,
        lambda data: int(data["artnetPackets"]) > before_packets
        and data["artSyncActive"] is True
        and data["artSyncPending"] is True,
    )

    step(
        "ArtDmx buffered by ArtSync: "
        f"artnetPackets={status['artnetPackets']}, "
        f"pending={status['artSyncPending']}"
    )

    step("Sending second ArtSync; buffered ArtDmx should flush")
    send_artnet_packet(unode_ip, make_artsync())

    status = wait_for_status(
        unode_client,
        lambda data: int(data["artSyncs"]) > before_syncs + 1
        and data["artSyncActive"] is True
        and data["artSyncPending"] is False,
    )

    step(
        "ArtSync flush complete: "
        f"syncs={status['artSyncs']}, pending={status['artSyncPending']}"
    )


def test_artsync_timeout_flushes_pending_artdmx_and_returns_to_async(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    _config, universe = _configure_artnet_output_for_artsync(
        unode_client,
        preserved_config,
    )
    before = unode_client.get_json("/api/status")
    before_syncs = int(before["artSyncs"])
    before_packets = int(before["artnetPackets"])
    before_timeouts = int(before["artNetDiagnostics"]["syncTimeouts"])

    step("Sending ArtSync to enable synchronous ArtDmx output mode")
    send_artnet_packet(unode_ip, make_artsync())

    wait_for_status(
        unode_client,
        lambda data: int(data["artSyncs"]) > before_syncs
        and data["artSyncActive"] is True
        and data["artSyncPending"] is False,
    )

    step("Sending ArtDmx that should remain pending until ArtSync timeout")
    send_artnet_packet(
        unode_ip,
        make_artdmx(
            universe,
            [55, 66, 77, 88],
            sequence=0,
        ),
    )

    pending = wait_for_status(
        unode_client,
        lambda data: int(data["artnetPackets"]) > before_packets
        and data["artSyncActive"] is True
        and data["artSyncPending"] is True,
    )
    step(
        "ArtDmx pending before timeout: "
        f"artnetPackets={pending['artnetPackets']}, "
        f"syncTimeouts={pending['artNetDiagnostics']['syncTimeouts']}"
    )

    step("Waiting for ArtSync timeout to flush pending data")
    timed_out = wait_for_status(
        unode_client,
        lambda data: data["artSyncActive"] is False
        and data["artSyncPending"] is False
        and int(data["artNetDiagnostics"]["syncTimeouts"]) > before_timeouts,
        timeout=6.0,
        interval=0.2,
    )

    step(
        "ArtSync timeout complete: "
        f"syncTimeouts={timed_out['artNetDiagnostics']['syncTimeouts']}, "
        f"artSyncActive={timed_out['artSyncActive']}, "
        f"pending={timed_out['artSyncPending']}"
    )
