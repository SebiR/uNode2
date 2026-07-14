# uNode Mini Manual

uNode is a compact ESP8266-based Art-Net 4, sACN / ANSI E1.31, and DMX512
interface. It can operate as either a network-to-DMX output node or a
DMX-to-network input node. Device configuration, monitoring, testing, and
diagnostics are available through the integrated web interface.

Art-Net management remains active so controllers can still discover, identify,
locate, and configure the node. The **Live Protocol** setting selects whether
live DMX data is transported as ArtDmx or as sACN multicast.

## Quick Start

1. Power the uNode.
2. Connect to its access point if it has not yet been configured for an
   existing Wi-Fi network.
3. Open `http://2.0.0.1` in a browser.
4. Select the required Wi-Fi mode, live protocol, Port-Address/Universe, and
   data direction.
5. Choose **Save** or **Save & Restart** in the status bar. Art-Net/DMX changes
   are applied live; network changes restart the node and the page reloads
   automatically.

The default access-point credentials are generated from the ESP8266 chip ID:

- SSID: `uNode_<CHIP_ID>`
- Password: `artnode<CHIP_ID>`
- Address: `http://2.0.0.1`

The hexadecimal chip ID is displayed in the web interface.

## Live Protocol and Data Directions

| Live Protocol | Behaviour |
|---|---|
| Art-Net / ArtDmx | Uses ArtDmx for live DMX data. Art-Net discovery and management are available. |
| sACN / E1.31 | Uses multicast sACN Data Packets on UDP port `5568` for live DMX data. Art-Net discovery and management remain available. |

| Direction | Network side | Physical side | Typical use |
|---|---|---|---|
| Network to DMX | Receives ArtDmx or sACN | Outputs DMX512 | Driving fixtures from a lighting controller |
| DMX to Network | Sends ArtDmx or sACN | Receives DMX512 | Bringing a physical DMX source onto the network |

The RS-485 transceiver direction is changed automatically when the configured
mode changes.

In DMX-to-Art-Net mode, uNode sends ArtDmx by unicast to discovered subscribers
that advertise the configured Port-Address. In DMX-to-sACN mode, uNode sends
sACN multicast to the configured Universe. A frame is sent after DMX data
changes and at least once per second while DMX input remains active.

## Art-Net Addressing

The node uses the Art-Net 15-bit Port-Address:

```text
Port-Address = (Net × 256) + (Subnet × 16) + Universe
```

| Field | Valid range |
|---|---:|
| Net | 0-127 |
| Subnet | 0-15 |
| Universe | 0-15 |

For sACN, this same configured Port-Address is used as the sACN Universe. Since
sACN Universe `0` is invalid, a configured Port-Address of `0` is transmitted
and received as sACN Universe `1`.

## Implemented sACN / ANSI E1.31 Functions

The first sACN implementation focuses on live DMX data transport:

- Receives sACN Data Packets on UDP port `5568`.
- Joins the multicast group for the configured Universe when possible.
- Validates the ACN packet identifier, root/framing/DMP vectors, PDU lengths,
  Universe, property count, and DMX start code layout.
- Tracks sources by CID with sequence handling.
- Uses packet priority to ignore lower-priority sources while a higher-priority
  source is active.
- Supports Stream Terminated packets.
- Applies the configured output failsafe after approximately five seconds
  without valid sACN data.
- Sends DMX input frames as sACN multicast with source name, CID, priority,
  Universe, and sequence number.

Not currently implemented:

- sACN Universe Discovery.
- sACN Synchronization packets.
- Full per-address sACN priority/merge behaviour.

## Implemented Art-Net Functions

### ArtDmx

- Receives and validates ArtDmx packets in Art-Net-to-DMX mode.
- Accepts data only for the configured Port-Address.
- Supports payloads up to 512 DMX slots.
- Tracks non-zero incoming ArtDmx sequence numbers per sender and rejects
  stale or duplicate packets. Sequence `0` is treated as sequencing disabled.
- Sends ArtDmx in DMX-to-Art-Net mode.
- Uses an incrementing, non-zero ArtDmx sequence number when transmitting.
- Sends one copy per unique subscriber IP address.

### ArtSync

In Art-Net-to-DMX mode, uNode supports ArtSync for synchronized output.

After an ArtSync packet is received, the node enters synchronized output mode
for four seconds. During that window, matching ArtDmx packets update the
internal source/merge buffers but are not written to the physical DMX output
immediately. The next ArtSync packet flushes the pending merged frame to DMX.

If no further ArtSync packet is received for four seconds, uNode returns to
normal asynchronous ArtDmx output. Any pending frame is applied when leaving
sync mode so the output does not remain stale.

### ArtPoll and ArtPollReply

- Receives broadcast and unicast ArtPoll packets.
- Supports targeted ArtPoll Port-Address ranges.
- Sends delayed unicast ArtPollReply packets to the requester.
- Advertises node names, IP and MAC addresses, firmware version, DHCP state,
  port direction, Port-Address, activity state, and indicator state.
- Sends ArtPoll periodically in DMX-to-Art-Net mode.
- Parses received ArtPollReply packets and maintains a subscriber list.
- Removes subscribers that are no longer visible.
- Supports up to 16 subscriber bindings and avoids duplicate ArtDmx
  transmissions to the same IP address.

For older Art-Net 3 tools, the web interface provides a legacy ArtPollReply
compatibility option. When enabled, uNode keeps the Art-Net 3 fields intact but
clears the Art-Net 4 extension bytes that occupy former filler space. ArtDmx
and ArtPoll behaviour are unchanged.

### ArtIpProg

uNode supports ArtIpProg and replies with ArtIpProgReply. The following remote
network programming operations are implemented:

- DHCP enable.
- Static IP address.
- Static subnet mask.
- Static default gateway.
- Restore uNode's factory network defaults.
- Enquiry-only requests.

Received values are validated with the same semantic IPv4 checks used by the
web interface. Accepted changes are stored in `/config.json`, acknowledged with
ArtIpProgReply, and then applied by an automatic restart. The fixed recovery/AP
address `2.0.0.1` is intentionally not changed by ArtIpProg; the command affects
the station/client network configuration.

### ArtAddress

The following ArtAddress operations are implemented:

- Program the Art-Net Port Name.
- Program the Art-Net Long Name.
- Store changed names in the persistent configuration.
- Set indicators to **Normal**.
- Set indicators to **Mute**.
- Set indicators to **Locate**.
- Set output failsafe to **Hold**.
- Set output failsafe to **All to Zero**.
- Set output failsafe to **All to Full**.
- Set output failsafe to **Failsafe Scene**.
- Record the current output as failsafe scene.
- Program Net, Sub-Net, and the active port's SwIn or SwOut Universe.
- Switch Port 0 live to DMX output with `AcDirectionTx0`.
- Switch Port 0 live to DMX input with `AcDirectionRx0`.
- Select Port 0 merge mode with `AcMergeLtp0` and `AcMergeHtp0`.
- Cancel the current merge state with `AcCancelMerge`.
- Return an updated ArtPollReply to the requester.

ArtAddress Port-Address fields are applied only when the programming bit
`0x80` is set, as required by the specification. Because uNode has no physical
address switches, reset-to-switch values are ignored.

Port-direction commands are stored persistently and applied immediately by
restarting the DMX UART in the requested mode. Switching to DMX input also
flushes the subscriber list and starts a new ArtPoll discovery cycle, as
required for `AcDirectionRx0`.

### ArtDmx Output Merge

In Art-Net-to-DMX mode, uNode supports two active ArtDmx sources for the
configured Port-Address. Sources are identified by sender IP address and the
ArtDmx Physical field.

The Output Merge setting controls how the two sources are combined:

- **HTP**: each DMX slot uses the higher value from the two sources.
- **LTP**: the most recently received ArtDmx source drives the complete output
  frame.

When only one source is active, that source drives the output directly. A third
simultaneous source for the same Port-Address is ignored. If one merge source
stops transmitting, it is removed after the Art-Net ten-second merge timeout
and the remaining source continues. If all ArtDmx input disappears, the normal
configured output failsafe takes over.

The merge mode can be changed from the web interface or remotely with
ArtAddress. `AcCancelMerge` clears the current merge on the next ArtDmx packet;
the sender of that packet takes control and other sender IP addresses are
ignored while it remains active. uNode advertises active merge state and LTP
mode in ArtPollReply GoodOutputA.

## Output Failsafe

In Art-Net-to-DMX mode, uNode detects loss of valid ArtDmx for the configured
Port-Address after approximately five seconds. The configured output failsafe
is then applied once and remains active until new valid ArtDmx arrives.

Available modes:

| Mode | Behaviour |
|---|---|
| Hold | Keep the last valid DMX output frame. |
| All to Zero | Set all 512 DMX channels to `0`. |
| All to Full | Set all 512 DMX channels to `255`. |
| Failsafe Scene | Output the recorded 512-channel failsafe scene. |

The failsafe scene is stored as `/failsafe.bin` in LittleFS. If Failsafe Scene
is selected but no valid scene exists, uNode outputs zero as a safe fallback
and reports the condition in NodeReport.

The selected failsafe mode and programmable-failsafe support are advertised in
ArtPollReply `Status3`. The mode can be changed through the web interface or
with the ArtAddress failsafe commands.

### Packet Validation

Incoming packets are checked for:

- The `Art-Net` packet identifier.
- Supported protocol revision.
- Minimum packet length for the detected opcode.
- Valid and available ArtDmx payload length.
- Valid ArtAddress BindIndex.
- Maximum UDP receive-buffer size.

ArtNzs packets are recognized and validated by the protocol layer, but the
application does not currently process non-zero-start-code data.

## Wi-Fi Modes

| Mode | Behaviour |
|---|---|
| Client | Connects to an existing Wi-Fi network. DHCP or a static IPv4 configuration can be used. |
| Access Point | Creates the uNode access point at `2.0.0.1`. No external network is required. |
| AP + Client | Keeps the uNode access point active while also connecting to an existing Wi-Fi network. |

When connected as a client, the node is also available through mDNS at:

```text
http://<hostname>.local
```

### Connection Recovery

- Client reconnection uses an exponential delay from 1 to 60 seconds.
- In Client mode, the node keeps reconnecting in the background when the
  configured network is unavailable.
- Recovery access is intentionally only available when the hardware recovery
  button is held during power-on or reset.
- In AP + Client mode, the access point intentionally remains active.

The WiFiManager configuration portal also uses `2.0.0.1` and is indicated by
the amber status-LED pattern described below.

### Saved Wi-Fi Credentials

The ESP8266 stores at most one station SSID/password pair in SDK flash. uNode
does not maintain a multi-network list.

The Network tab shows the currently stored station SSID when one is available.
Use **Forget Saved Wi-Fi Credentials** to erase only this stored SSID/password
pair. uNode configuration, Art-Net settings, the web password, and failsafe
scene data are left unchanged. The same action is available from Recovery Mode.

## OTA Updates and Recovery

The firmware provides HTTP OTA updates for both firmware and the complete
LittleFS filesystem image.

- Firmware updates replace only the application firmware.
- LittleFS updates replace the complete filesystem, including `/config.json`.
- Download the configuration before a LittleFS update if the existing settings
  should be preserved.
- Update files must match the configured `4M1M` flash layout.

Release artifacts can be generated with:

```powershell
.\tools\build_release.ps1
```

The script writes versioned firmware, LittleFS, and manifest files to
`artifacts/release`. File names contain only the firmware version, hardware
profile suffix, and artifact type; no build timestamp is added. Each release
run creates both the current hardware profile and the legacy hardware profile:

- `uNode-<version>-firmware.bin`
- `uNode-<version>-littlefs.bin`
- `uNode-<version>_legacy-firmware.bin`
- `uNode-<version>_legacy-littlefs.bin`
- `uNode-<version>-manifest.json`

The manifest includes both hardware profiles, flash layout, LittleFS image
size, and SHA-256 hashes.

Generated release artifacts can also be flashed over UART with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1
```

The UART helper lists available release artifacts, asks for the firmware/profile
number, lists USB serial adapters with VID/PID, and flashes firmware to `0x0`
and LittleFS to `0x300000` at 512000 baud by default. The selected adapter is
remembered in `artifacts/flash_uart.settings.json`, so the next run can pick the
same VID/PID and serial number automatically when exactly one match is present.

Useful options are `-ListOnly`, `-Port COMx`, `-FirmwareOnly`, `-LittleFsOnly`,
`-Baud <rate>`, and `-NoRemember`.

Release artifacts can also be uploaded through the normal web OTA endpoints:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_ota.ps1 -FirmwareOnly -NodeIp 2.0.0.1
powershell -ExecutionPolicy Bypass -File .\tools\flash_ota.ps1 -LittleFsOnly -NodeIp 2.0.0.1
```

Use `-Password <password>` when the web/API password is enabled. Firmware and
LittleFS OTA updates are deliberately one-step operations because each accepted
upload restarts the node. For a full update, run the helper once for firmware
and once for LittleFS after the node is reachable again.

The Arduino sketch lives in `firmware/uNode_2`. Open
`firmware/uNode_2/uNode_2.ino` in the Arduino IDE if you want to build or edit
the firmware manually.

While the project is below `1.0.0`, completed feature blocks should increment
the minor version, for example `0.2.0` to `0.3.0`. Patch versions are reserved
for focused bug-fix or hotfix builds.

User-facing changes, compatibility notes, and intentional breaking changes are
tracked in `CHANGELOG.md`.

### Recovery Mode

Hold the recovery button during power-on or reset to enter firmware-embedded
recovery mode. The default recovery button pin is GPIO14, active-low with
`INPUT_PULLUP`.

Recovery mode:

- Starts a recovery access point at `2.0.0.1`.
- Serves a minimal web page from firmware/PROGMEM, independent of LittleFS.
- Provides firmware upload, LittleFS upload, factory reset, and restart.
- Disables the normal Art-Net, DMX, WebSocket, and LittleFS web application.

After an update-triggered restart, the node enters recovery mode again only if
the recovery button is still held during reset. Otherwise it boots into normal
operation.

If LittleFS cannot be mounted during normal boot, the node shows the fault LED
pattern and waits for a power-cycle with the recovery button held.

## Status LEDs

The default hardware uses two WS2812-compatible pixels connected to GPIO4:

1. Network/status LED
2. Art-Net/DMX activity LED

The pixel color order can be changed at compile time with
`LED_WS2812_COLOR_ORDER`. Global brightness is configurable in the web
interface.

### Network/Status LED

| Color and pattern | Meaning |
|---|---|
| Solid red | Wi-Fi disconnected |
| Flashing red, 500 ms toggle interval | Connecting during startup |
| Flashing orange, 150 ms toggle interval | WiFiManager configuration portal active |
| Fast flashing red, 120 ms toggle interval | LittleFS boot fault; reboot with recovery button held |
| Brief blue pulse every second | Access point is available, but no station is connected |
| Solid blue | Access point is active and at least one station is connected |
| Solid green | Wi-Fi client connected with at least 50% signal quality |
| Green with brief amber pulse every two seconds | Wi-Fi client connected, signal quality below 50% |
| Green with brief red pulse every two seconds | Wi-Fi client connected, signal quality below 25% |
| Off | Indicators muted or LEDs disabled |

Legacy single-color hardware cannot show the WS2812 colors. It uses the same
logical patterns where possible: AP without a station blinks, AP with a station
is steady on, weak client signal briefly blanks the LED, and very weak client
signal inverts the pattern.

### Art-Net/DMX Activity LED

Activity pulses normally last approximately 50 ms.

| Color | Meaning |
|---|---|
| Off | No current activity |
| Green | Art-Net management or transmission activity |
| Cyan | Physical DMX input frame received |
| Amber | ArtDmx or sACN received and passed to physical DMX output |

### System Override Patterns

These patterns temporarily override the regular status and activity display.

| Pattern | Meaning |
|---|---|
| Alternating amber between both LEDs | Firmware or LittleFS update in progress |
| Both LEDs solid green | Update accepted; restart follows |
| Alternating red between both LEDs | Update failed or upload aborted; regular LED display resumes shortly |
| Alternating blue/red between both LEDs | Recovery Mode active |

### Art-Net Indicator Overrides

| Mode | Behaviour |
|---|---|
| Normal | Both LEDs show their regular status and activity patterns. |
| Mute | Both LEDs are switched off. |
| Locate | Both LEDs flash magenta with a 150 ms toggle interval. |

Normal, Mute, and Locate can be selected remotely through ArtAddress. Locate
can also be toggled from the web interface.

The two software LEDs in the dashboard mirror the colors rendered on the
physical LEDs.

### Direct LED API

External tools can temporarily take control of both indicators without
changing the saved configuration. The override is held only in RAM and is
automatically cleared by a reboot.

Read the current rendered colors and override state:

```http
GET /api/leds
```

Set both LEDs using either `#RRGGBB` strings or RGB component objects:

```http
POST /api/leds
Content-Type: application/json

{
  "network": "#123456",
  "activity": { "r": 171, "g": 205, "b": 239 }
}
```

Return control to the regular network and DMX status logic:

```http
POST /api/leds/release
```

The two POST endpoints require the normal `X-uNode-Auth` session token when
web access control is enabled. The configured global LED brightness still
applies. On Legacy hardware, black switches an LED off and every non-black RGB
value switches it on because the fitted indicators cannot reproduce colors.
Firmware-update and Recovery Mode patterns always have priority over a direct
API override.

## Hardware Controls

The current hardware build can control the RS-485 transceiver with separate
pins:

- GPIO5: active-low `/RE`
- GPIO12: active-high `DE`
- GPIO13: switchable bus termination control

At boot, split-control builds initialize the transceiver in a passive state:
`DE` low and `/RE` high. The configured DMX direction is applied when the DMX
runtime starts.

The Hardware tab provides a persistent termination mode:

| Mode | Behaviour |
|---|---|
| Off | Termination output is always disabled. |
| On | Termination output is always enabled. |
| Auto | Termination is enabled in DMX input mode and disabled in DMX output mode. |

The same tab reports whether split `/RE`/`DE` control and switchable
termination are available in the current build, plus the effective driver,
receiver, and termination states.

The local hardware button is active-low on GPIO14. Holding it during power-on
or reset always enters Recovery Mode. During normal operation, the Hardware tab
can either leave the button deactivated or use a debounced short press to toggle
the local Art-Net Locate indication.

The Hardware tab also provides optional Bus Guarding:

| Mode | Behaviour |
|---|---|
| Off | The configured DMX direction is used immediately at boot. |
| Auto input on boot | uNode briefly listens for external DMX while keeping the RS-485 driver disabled. If at least two valid DMX frames are detected, the node switches to DMX input and stores that direction. |

Bus Guarding is a boot-time convenience feature, not continuous collision
detection. It does not monitor for another master after the configured DMX
direction has started.

Legacy builds can disable split control and termination at compile time. In
that case the web interface reports the hardware controls as unavailable rather
than exposing a runtime-selectable hardware revision.

## Web Interface

The integrated web interface provides:

- General device, network, firmware, flash, and filesystem information.
- Runtime diagnostics such as heap status, reset reason, boot count,
  configuration schema version, and installed/expected web-asset version.
- A Detailed Diagnostics page with Art-Net parser/runtime counters for protocol
  debugging.
- Network diagnostics for the IPv4 Fragment Guard, including discarded
  incoming fragments and rejected fragmented transmit attempts.
- A status-bar warning when ArtDmx arrives for the wrong Art-Net Port-Address.
- Wi-Fi signal quality and reconnection status.
- A browser-side connection watchdog that reports lost node connectivity and
  refreshes status/configuration automatically after reconnecting.
- ArtDmx, ArtPoll, DMX, and frame-rate counters.
- ArtSync counters and synchronized/asynchronous output state.
- A monitor for the first 32 DMX channels.
- Art-Net name, direction, and Port-Address configuration.
- Legacy ArtPollReply compatibility mode for older Art-Net 3 tools.
- Subscriber discovery and a list of matching Art-Net devices.
- Output failsafe mode and failsafe-scene recording.
- Client, Access Point, and AP + Client Wi-Fi configuration.
- DHCP and static IPv4 configuration.
- A dedicated Hardware tab for LED brightness and board-level RS-485 options.
- RS-485 split-control and termination status when supported by the build.
- A global Locate button in the header; the same indicator reflects local and
  Art-Net-triggered Locate state.
- A browser-local theme selector with Auto, Light, and Dark modes.
- Four-channel DMX testing with Start Address, temporary override, Full On,
  Blackout, and manual override release.
- Firmware and complete LittleFS OTA upload.
- Configuration download and validated upload.
- Live saving for Art-Net/DMX runtime settings and manual restart with
  automatic browser reconnection and reload.

The DMX Test page acts as a temporary four-channel test desk. The Start Address
selects the first controlled channel, and the four faders control consecutive
channels. Moving a fader, Blackout Visible, or Full On Visible starts a local
test override. The override is not stored and automatically falls back to the
real Art-Net or physical DMX source after 10 seconds without test activity.
Release Override ends it immediately.

Art-Net/DMX settings saved from the web interface are applied live whenever
possible. This includes Port Name, Long Name, direction, Net/Sub/Universe,
failsafe mode, merge mode, legacy ArtPollReply mode, and LED brightness.
Changing network settings such as hostname, Wi-Fi mode, DHCP/static IP, subnet,
or gateway still requires a restart.

### Optional Write Protection

The web interface can be used read-only without logging in. When an admin
password is configured in the System tab, settings and output-affecting actions
are locked until the browser logs in with the status-bar Login button. The
session token is kept only in RAM and is lost after logout, browser session
clear, or node reboot.

Leaving the password field empty and applying the setting disables write
protection. If the password is forgotten, recovery mode provides a password
reset action that clears the password. Set a new password from the normal
System tab after rebooting from Recovery Mode.

## Configuration Storage

The active configuration is stored as `/config.json` in LittleFS. Writes use a
temporary file and backup rename sequence to reduce the risk of corruption.
Uploaded JSON configurations are parsed and validated before replacing the
active configuration.

Mutating web endpoints reject oversized request bodies before parsing. Uploaded
configuration files are limited to 8 KiB; firmware and LittleFS OTA uploads are
checked against the declared upload size and the configured flash layout.

Configuration files include a `configVersion` field. Firmware currently uses
schema version `3`; older configuration files without this field are migrated
and saved again automatically when loaded.

The configuration contains:

- Config schema version.
- Hostname and Wi-Fi mode.
- DHCP or static IPv4 settings.
- LED brightness.
- Art-Net Port Name and Long Name.
- Art-Net/DMX direction.
- Net, Subnet, and Universe.
- Output failsafe and merge mode.
- Hardware termination mode.

Configuration files can be downloaded before maintenance and uploaded again
afterwards.

## Development Logging

Serial logging is disabled in the normal release build. When enabled at compile
time with `ENABLE_SERIAL_LOG=1`, log output uses `Serial1` on UART1 TX / GPIO2
at `115200` baud by default. This keeps UART0 available for DMX, so physical
DMX input and output can continue to run while debug messages are transmitted.

Available compile-time verbosity levels are:

`LOG_LEVEL_ERROR`, `LOG_LEVEL_WARN`, `LOG_LEVEL_INFO`, `LOG_LEVEL_DEBUG`, and
`LOG_LEVEL_TRACE`.

Example debug build flags:

`-DENABLE_SERIAL_LOG=1 -DLOG_VERBOSITY=LOG_LEVEL_DEBUG`

UART1 on the ESP8266 is TX-only. GPIO2 is also a boot-strapping pin and must not
be pulled low during reset. Use a high-impedance serial adapter input and avoid
external circuitry that can hold GPIO2 low at boot.

If logging is intentionally moved back to UART0 by overriding `LOG_SERIAL_PORT`
to `Serial`, set `SERIAL_LOG_REPLACES_DMX=1` as well because UART0 is shared
with DMX on this hardware.

## Current Limitations and Planned Features

The following features are not implemented yet:

- RDM and ArtRdm.
- Application-level ArtNzs processing.
- sACN Universe Discovery and Synchronization packets.
- User-configurable sACN source CID/UUID and priority.
- Automatic rollback after a faulty firmware update.

Art-Net-specific remote configuration functions such as ArtAddress and
ArtIpProg remain Art-Net management features. sACN is currently used only for
live DMX data transport.

The target hardware contains 4 MB of flash. The intended build layout is
`4M1M`, providing a dedicated LittleFS area and sufficient firmware-update
space.

## Maintenance Notes

- A firmware update does not normally replace LittleFS or its configuration.
- Uploading a complete LittleFS image replaces the entire filesystem,
  including `/config.json`.
- The LittleFS image contains `/version.json` with the web-interface asset
  version. The dashboard warns when the installed web files do not match the
  running firmware.
- Download the configuration before a LittleFS update if the existing settings
  should be restored afterwards.
- After changing files in `firmware/uNode_2/data`, upload a new LittleFS image
  for the web-interface changes to appear on the device.
- Factory reset is available from the firmware-embedded recovery page, not from
  the normal web interface.
