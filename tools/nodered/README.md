# uNode Node-RED Test Dashboard

This optional dashboard polls `http://2.0.0.1/api/status` every five seconds.
It is intended for the Raspberry Pi test rig where Ethernet provides
SSH/Internet access and Wi-Fi is dedicated to the uNode access point.

The dashboard can start either of the guarded soak profiles:

- **Network soak** exercises Art-Net and sACN without the RP2040 fixture.
- **DMX HIL soak** exercises Art-Net and sACN through the RP2040 DMX fixture.

The selected duration is applied once to each protocol, so a one-hour selection
takes approximately two hours in total. A shared `flock` prevents two dashboard
or wrapper-started soak tests from using the fixture at the same time. Test
progress remains visible in the live pytest log.

The regression controls can run the regular integration suite with selectable
RP2040 DMX/HIL, button GPIO 8, reset GPIO 7, one-minute soak, and safe OTA
coverage. The OTA hardware profile is selectable when OTA coverage is enabled.
Destructive OTA recovery tests deliberately remain command-line only.

The separate **Node Updater** page is intended for completed devices. It scans
`wlan0` for factory-style `uNode_XXXXXX` access points, briefly connects to each
one, and reports firmware, web-asset, normal/recovery, signal, and inferred
hardware-profile information. A selected node can then receive firmware,
LittleFS, or both from a size- and SHA-256-verified release manifest. The
newest complete local release is selected by default, while older releases
remain available for deliberate downgrade/recovery work.

If `wlan0` is already associated with a uNode AP, discovery briefly
disconnects it before scanning. This avoids adapter/driver scans that expose
only the currently associated ESP8266 AP. The previous connection is restored
after inventory; if Wi-Fi was originally idle, it is returned to idle instead
of remaining connected to the final node.

The separate **Hardware Test** page contains a **Status LED Test** card. It uses
the stored node inventory from the updater, connects the Pi to the selected AP,
and exposes separate color pickers for the network and Art-Net/DMX WS2812
pixels. Apply creates a volatile override; Release returns control to firmware
status logic. Capability data from `/api/status` disables the controls for
Legacy hardware, Recovery Mode, and older firmware that does not provide the
RGB API.

Normal-mode LittleFS updates archive the complete configuration under
`artifacts/node_backups/` and restore it after the image restart. Recovery mode
has no configuration-download endpoint; firmware-only recovery is therefore
non-destructive, while a recovery LittleFS update explicitly installs release
defaults. The updater derives the factory AP credential from the validated
chip-ID SSID and accepts an optional GUI password for access-controlled nodes.

Updater jobs and regression/soak jobs share the same fixture lock. A scan or
update is rejected while a test is running, and a test cannot start while an
update owns `wlan0`.

The same page also provides **Initial USB Flash** for blank or reworked nodes.
It enumerates stable `/dev/serial/by-id/` devices, prefers the CP210x production
adapter, retains CH340 compatibility for the current bench setup, and excludes
the RP2040 test tool. Espressif `esptool` uses the adapter's DTR/RTS wiring to
enter the ESP8266 ROM bootloader automatically. The
backend reads the chip ID and flash ID first, requires the 4MB layout, then
writes and verifies firmware at `0x000000` plus the complete LittleFS image at
`0x300000` in one operation. A successful factory flash is only reported after
the matching `uNode_XXXXXX` AP has appeared. An optional full-chip erase is
available for deliberately reworked devices; regular initial flashing already
replaces the complete application and filesystem regions.

`esptool` is installed with the regular Linux test-host requirements:

```bash
tools/bootstrap_test_host.sh
```

An active job can be cancelled from the dashboard. The wrapper sends `SIGINT`
to the isolated pytest process group, allowing test fixtures to restore the
saved node configuration before the job is marked `cancelled`. Soak and
regression runs share the same lock and cannot run concurrently.

Install or update the flow locally on the Node-RED host:

```bash
cd ~/uNode2
sudo bash tools/nodered/install_networkmanager_policy.sh pi
.venv/bin/python tools/nodered/install_dashboard.py
```

The Polkit rule grants only the named local production user permission to scan
Wi-Fi and activate/manage NetworkManager profiles. It is required because the
Node-RED system service has no interactive desktop session in which to answer
NetworkManager authorization prompts. Newly discovered uNode APs are stored as
user-private connection profiles.

Open `http://printer.local:1880/unode/status`. The installer uses Node-RED's
single-flow Admin API and therefore leaves unrelated flows untouched. The
dashboard also tails `artifacts/test_reports/latest-run.log`, which is updated
live by `tools/test.sh` while pytest is running.

The updater is available at `http://printer.local:1880/unode/updater`. Its
progress log is stored as `artifacts/test_reports/latest-updater.log`.

The backend can also be inspected from a shell without touching Wi-Fi:

```bash
.venv/bin/python tools/nodered/node_updater.py status
.venv/bin/python tools/nodered/node_updater.py releases
```

The same guarded entry point can be used from a shell:

```bash
tools/nodered/run_test_job.sh host 3600
tools/nodered/run_test_job.sh dmx 3600
tools/nodered/run_test_job.sh regression rp2040,button,reset
tools/nodered/run_test_job.sh stop
tools/nodered/run_test_job.sh status
```
