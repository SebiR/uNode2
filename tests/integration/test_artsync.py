from __future__ import annotations

from artnet_packets import make_artdmx, make_artsync
from helpers import configured_port_address, send_artnet_packet, step, wait_for_status
from unode_client import UNodeClient


def test_artsync_buffers_artdmx_until_sync_packet(
    unode_client: UNodeClient,
    unode_ip: str,
    preserved_config: dict,
) -> None:
    config = preserved_config.copy()
    config["direction"] = 0  # Art-Net -> DMX

    step("Switching node to Art-Net -> DMX for ArtSync test")
    unode_client.save_config(config)

    universe = configured_port_address(config)
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
            sequence=21,
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
