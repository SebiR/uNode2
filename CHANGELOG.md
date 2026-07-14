# Changelog

All notable user-facing and compatibility-relevant changes are documented here.
Newest versions are listed first.

The project is still below `1.0.0`. Minor versions mark completed feature
blocks, while patch versions are reserved for focused bug-fix or hotfix builds.

Breaking changes, config migrations, and compatibility notes must be called out
explicitly in each release entry.

## [Unreleased]

### Changed

- Added a compile-time isolated production-test Wi-Fi harness. Explicit
  `ENABLE_TEST_HARNESS_API=1` builds can accept RAM-only fixture credentials,
  switch from the node AP to a Raspberry Pi hotspot, force a controlled Client
  outage, and verify recovery of HTTP, ArtPollReply, sACN multicast membership,
  and live packets without rebooting. Normal and Legacy release firmware omit
  both test endpoints and all temporary-credential state. The Pi test runner
  restores the node AP and its previous Wi-Fi connection automatically.
- Limited the direct RGB LED API to WS2812 hardware and exposed an explicit
  capability flag for external tools. Legacy builds no longer register the
  RGB endpoints instead of approximating arbitrary colors as simple on/off.
- Fixed Node-RED production discovery when the Pi is already connected to one
  uNode AP. The updater now scans from a temporarily disconnected Wi-Fi state,
  discovers nodes across all channels, restores the previous connection, and
  returns an initially idle adapter to idle after inventory. A scoped Polkit
  installer enables the non-interactive Node-RED service to switch APs, while
  newly discovered uNode networks use user-private connection profiles.
- Added an authenticated, volatile status LED API. Arbitrary RGB colors can
  temporarily override both WS2812 indicators until explicitly released.
  Critical firmware-update and Recovery Mode patterns retain priority.
- Added a Node-RED production updater page that discovers uNode access points,
  inventories normal and Recovery Mode firmware, and installs verified local
  firmware/LittleFS release artifacts. Normal-mode LittleFS updates archive
  and restore the node configuration; updater, regression, and soak jobs share
  an exclusive hardware-fixture lock.
- Extended the production updater with automatic initial USB programming. It
  identifies DTR/RTS-capable USB serial adapters, excludes the RP2040 fixture,
  verifies the ESP8266 chip ID and 4MB flash capacity, writes firmware and the
  complete LittleFS image at their validated offsets, checks both write hashes,
  and confirms that the resulting factory AP is advertised.
- Hardened oversized UDP handling for Art-Net and sACN. The portable Art-Net
  library now uses a bounded discard state machine for unknown UDP transports
  and supports an explicit constant-time discard capability for transports
  such as ESP8266 `WiFiUDP`. This keeps cooperative loop work bounded without
  tying the library to one network backend. Updated the bundled uNodeArtNet
  library to `0.1.2`.
- Added an IPv4 Fragment Guard for the ESP8266 network stack. uNode never needs
  fragmented live-data packets, so incoming fragments are discarded before
  lwIP reassembly can be abused by maximum-size UDP datagrams. Diagnostics
  report dropped RX fragments and rejected fragmented TX attempts.
- Added an explicit ESP8266 scheduler/Wi-Fi yield after every OTA upload
  block, matching the core HTTP update server and preventing fast full-size
  LittleFS uploads from starving the hardware watchdog.
- Fixed an sACN multicast-membership leak exposed by long SoftAP soak testing.
  The ESP8266 `WiFiUDP` implementation joins IGMP groups in
  `beginMulticast()` but does not leave them in `stop()`. uNode now owns the
  join/leave lifecycle explicitly on every socket rebind and reports multicast
  join, leave, failure, and rebind counters in diagnostics.
- Added regression coverage that cycles through more multicast Universes than
  the eight-entry lwIP IGMP pool, plus sustained 40 FPS sACN input while the
  HTTP API remains responsive.
- Host network-output soaks now drive Art-Net and sACN continuously at 40 FPS
  in a dedicated sender thread while control-plane, parser, and API checks run
  independently at their configured interval.
- Hardened long-running SoftAP operation after a host soak exposed a hardware
  watchdog reset followed by an unresponsive Wi-Fi stack. Wi-Fi status, RSSI,
  and SoftAP station-count queries are now rate-limited, while sACN receive
  bursts use a bounded per-loop packet budget so cooperative network and web
  processing cannot be starved.
- Integration reports now retain the node identity captured at test startup,
  so a network-stack lockup no longer produces an anonymous failure certificate.
- Soak failures now include the final reachability error and distinguish it
  from earlier transient failures that recovered within the grace period.
- Release builds now preserve matching ELF and linker MAP sidecars, including
  hashes in the manifest, so watchdog EPC addresses can be decoded against the
  exact shipped firmware image.
- Added the modified `LXESP8266DMX` implementation to the repository as local
  fork version `2.2.1-unode.1`. Release builds now consume the tracked copy,
  including UART0 TX, short-frame RX timeout handling, atomic frame APIs, and
  bounds/initialization hardening, instead of depending on an external Arduino
  sketchbook installation. The unique `uNodeESP8266DMX.h` entry point prevents
  Arduino from silently resolving the original global library instead.
- Added reusable `uNodeArtNet` reference examples for Wi-Fi ArtDmx receive,
  Ethernet ArtDmx receive, unicast ArtDmx transmit, and ArtPoll discovery. Each
  example now includes a purpose/data-flow/setup overview and explanatory
  comments around transport ownership, addressing, callbacks, and polling.
- Updated DMX-to-network dropout and latency HIL tests to use a continuous
  40 FPS DMX stream while changing slot values. This matches real DMX behavior
  and ensures each frame is closed by the following Break instead of testing
  isolated frames one update behind. Empty latency runs now report a clear
  no-samples failure instead of raising an `IndexError` in statistics output.
- Extended the RP2040 DMX tester to version `0.3.2`. Its onboard GPIO16
  WS2812 now indicates boot, idle/high-impedance state, RX/TX mode, DMX frame
  activity, and command errors without updating during active RX frames.
- Extracted the Art-Net parser, packet generation, ArtPollReply state, and
  management packet handling into the reusable `uNodeArtNet` Arduino library.
  The library now accepts the standard Arduino `UDP` interface plus an
  application-supplied network identity, removing all direct ESP8266/Wi-Fi
  dependencies and allowing Wi-Fi or Ethernet transports on other boards. The
  obsolete four-port internal DMX/UART buffers were removed; physical DMX is
  now exclusively an application concern and the uNode regains about 2 KiB of
  static RAM.
- Serial debug logging is now disabled by default for normal and release builds
  to reduce RAM pressure and avoid unnecessary UART1 output in production.
- Updated the web interface header logo asset and constrained its top-bar
  sizing for the wider IllumiNocte wordmark.
- Extended the RP2040 DMX tester to version `0.3.1` with safe auxiliary GPIO
  JSONL commands (`read`, `input`, `write`, `pulse`, `release`) on GPIO6/7/8
  by default, plus Python helpers and optional HIL coverage for the uNode local
  button.
- Test reports and generated production certificates now include the resolved
  RP2040 tester port, tester firmware version, current tester mode, and
  advertised auxiliary GPIO pins when the RP2040 HIL fixture is used.
- The local hardware button now has separate runtime actions for short and long
  presses. Short press can toggle Locate, while long press can immediately
  toggle status LED mute.
- The web header now shows a bulb-off indicator while status LEDs are muted,
  and ArtAddress Normal/Locate can clear LED mute again.
- LED brightness is now limited to 1..100% in the web UI and configuration;
  complete LED blackout is handled by the separate temporary LED Mute control.
- Holding the local hardware button during boot remains reserved for Recovery
  Mode.
- Added dedicated system LED override patterns for OTA/recovery states:
  alternating amber while firmware or LittleFS upload is running, solid green
  after an accepted update, short alternating red after update failure, and
  alternating blue/red in Recovery Mode.
- Recovery Mode can now only clear the web password. New passwords are set from
  the normal System page after rebooting.
- Physical DMX output activity now uses amber instead of yellow for better
  separation from green Art-Net activity on WS2812 status LEDs.
- The network status LED now indicates weak Wi-Fi signal quality in client mode:
  connected nodes stay green above 50%, blink amber below 50%, and blink red
  below 25%. Legacy single-color LEDs use matching off/on blink patterns.
- In AP mode, the network status LED now flashes while the AP is available but
  no station is connected, and turns steady blue once a station has joined.
  Legacy single-color LEDs turn steady on once a station has joined.
- sACN Universe is now shown explicitly in the Protocol page and follows the
  configured Universe value used by controllers such as DMX Workshop.
- sACN priority handling now keeps lower-priority sources warm and falls back
  to the best remaining active source when a higher-priority source sends
  Stream_Terminated or times out.
- Reduced the volatile event log and sACN source table sizes to keep more heap
  headroom on ESP8266 builds.
- Added low-heap headroom monitoring that records throttled runtime warnings in
  the volatile event log and exposes the active warning state in `/api/status`.
- Added a volatile in-memory event log for important runtime warnings,
  including protocol mismatches, wrong-universe packets, and output failsafe
  activation. The System page can display, download, and clear the current log.
- Protocol-mismatch status warnings now trigger only when the matching drop
  counter increases, so old counters no longer keep re-triggering the banner.
- Added protocol-mismatch diagnostics and a status-line warning when ArtDmx is
  received while sACN is selected, or sACN is received while Art-Net is selected.
- Added persistent sACN Source Name and Priority settings to the Protocol page,
  status API, WebSocket status, and outgoing sACN packets.
- Added sACN counters to the Detailed Diagnostics page while keeping the
  dashboard focused on high-level protocol activity.
- sACN now counts valid packets dropped because sACN live data is disabled or
  the node is currently configured for DMX input.
- Updated sACN network-data-loss handling to use the E1.31 2.5 second timeout
  instead of the previous 5 second live-data timeout.
- Added a `USE_LEGACY_HARDWARE` build define that selects the original
  hardware profile with classic PWM status LEDs, tied RS-485 RE/DE direction
  control, and no switchable termination.
- Added a UART flash helper that selects release artifacts, lists serial ports
  with VID/PID, remembers the selected USB serial adapter, and flashes firmware
  plus LittleFS at 512000 baud by default.
- Added an OTA flash helper that selects release artifacts and uploads either
  firmware or LittleFS through the node's web update endpoints, including
  optional API-password login.
- Made the RP2040 DMX tester's TX/RX/direction pin defines override-friendly
  and documented automatic RS-485 direction handling.
- Added optional boot-time RS-485 Bus Guarding. When enabled, the node briefly
  listens for external DMX at startup and switches to DMX input when valid DMX
  is already present on the bus.
- Updated the release build script to generate both normal and legacy hardware
  artifacts in one run, using version-only file names without build timestamps.
- Added ArtPoll-based uNode auto-discovery to the PowerShell test runner when
  integration tests are started without an explicit `-NodeIp` or `-BaseUrl`.
- Added an initial sACN / ANSI E1.31 live-data mode. Art-Net management remains
  active, while live DMX data can now be selected as ArtDmx or sACN multicast.
- Added sACN packet validation, multicast Universe receive, DMX-to-sACN
  multicast transmission, source/CID sequence tracking, priority drops, stream
  terminated handling, timeout failsafe, status counters, and unit packet tests.
- Increased the configuration schema version to `4` for the new live protocol
  setting and Bus Guarding migration.

### Fixed

- Fixed a malformed HTML wrapper in the Protocol page that could cause later
  GUI tabs to render empty after the sACN settings card.
- Made the Network tab's "Forget Saved Wi-Fi Credentials" action use
  WiFiManager's ESP8266 persistent credential erase path instead of relying on
  a plain disconnect call.

### Tests

- Expanded soak testing profiles: host-only soak now covers Art-Net -> DMX and
  sACN -> DMX, while RP2040 HIL DMX-input soak now covers DMX -> Art-Net and
  DMX -> sACN. The soak tests continue to watch Boot Count, reset diagnostics,
  reachability, and heap health.
- Added sACN priority fallback coverage for warm lower-priority sources after
  Stream_Terminated and source-loss timeout.
- Added hardware-in-the-loop checks for sACN output failsafe behavior
  covering Hold, All-to-Zero, All-to-Full, and Backup Scene.
- Added sACN hardening coverage for short frames, malformed packets,
  protocol/direction drops, and sequence wraparound.
- Added regression coverage for configurable sACN Source Name and Priority,
  including verification on outgoing DMX-to-sACN packets.

## [0.21.0] - 2026-06-29

### Fixed

- ArtAddress `AcCancelMerge` now locks the next accepted ArtDmx source by both
  sender IP and Physical field, matching the `IP + Physical` source identity
  used by ArtDmx merging and sequencing.
- DMX-to-Art-Net forwarding now preserves the received physical DMX frame
  length instead of always transmitting 512-slot ArtDmx packets. Local test
  overrides and Art-Net-to-DMX output paths continue to use full 512-slot
  frames.

### Tests

- Added hardware-in-the-loop coverage for HTP and LTP ArtDmx merging with two
  Physical sources from one test host.
- Added merge edge-case tests for stale source timeout, third-source rejection,
  and ArtAddress `AcCancelMerge`.
- Strengthened the short-frame DMX input HIL test to require that a 6-slot DMX
  input frame is forwarded as a short, even-length ArtDmx packet instead of
  being expanded to a full 512-slot packet.
- Added API authentication regression coverage for protected write endpoints,
  config download, login failure/success, and logout token invalidation.

## [0.20.0] - 2026-06-28

### Changed

- Reworked the web interface with the new technical light/dark design used in
  the signal-flow mockup.
- Replaced the classic dashboard cards with a live signal-flow dashboard plus
  compact statistics.
- Moved login/logout into the System tab's Access Control card and added a
  lock indicator next to the node ID in the header.
- Kept static IP values visible while DHCP is selected, but disabled the fields
  until Static IP mode is active.
- Modernized OTA controls and disabled update buttons until matching files are
  selected.

## [0.19.6] - 2026-06-28

### Fixed

- Legacy Art-Net 3 PollReply generation now clears Art-Net 4 extension fields
  only in the transmitted legacy copy instead of mutating the persistent
  ArtPollReply state.
- Integration UDP reply helpers now bind to the local IPv4 interface used to
  reach the node, improving reliability on multi-interface Windows hosts.
- PollReply bit integration tests now accept DHCP-configured nodes when the
  temporary test configuration uses DHCP.
- DMX output timing HIL test now avoids counting a partial analyzer frame
  captured immediately after clearing RP2040 timing statistics.
- Integration REST client now retries short-lived HTTP transport interruptions
  such as incomplete reads during hardware-in-the-loop runs.

## [0.19.5] - 2026-06-28

### Fixed

- WebSocket dashboard updates now include ArtSync runtime fields so the compact
  ArtSync row no longer flickers between real values and zero.
- WebSocket updates now include the DMX test override timeout mode so the
  override status remains consistent between HTTP status polls.

## [0.19.4] - 2026-06-28

### Changed

- Made the dashboard more compact by combining related counters and "last seen"
  ages into single status rows for ArtDmx, ArtSync, ArtPoll, and DMX runtime
  information.

## [0.19.3] - 2026-06-28

### Added

- Added DMX Test patterns for Channel Chase and Find Address with configurable
  scan range, speed, pause/resume, previous/next, and stop controls.
- Added a non-persistent DMX test option to disable the local override timeout
  until the next node restart.
- Fixed Find Address so it starts paused on the first scan channel instead of
  running an automatic chase first.

## [0.19.2] - 2026-06-28

### Added

- Added a Revert button next to the unsaved-changes save action so accidental
  web UI edits can be discarded without reloading the page.
- Added compact status-bar messages for firmware/web-asset mismatch, active
  output failsafe, DMX test override, and recent wrong-universe ArtDmx packets.

### Changed

- Dashboard Art-Net and DMX cards now adapt their labels and summary values to
  the configured direction, showing Art-Net input/DMX output or DMX input/
  Art-Net output context more clearly.

## [0.19.1] - 2026-06-28

### Fixed

- The web root now returns a clear HTTP 500 error when `/index.html` is missing
  instead of silently failing the request.

### Changed

- Updated the roadmap to reflect implemented AP/AP+Client mode handling,
  scheduled restarts, recovery diagnostics, hardware-in-the-loop soak coverage,
  DMX fault injection, and DMX hardware-test coverage.

## [0.19.0] - 2026-06-28

### Changed

- Reorganized the repository into a workspace layout.
- Moved the ESP8266 Arduino sketch and LittleFS web assets to
  `firmware/uNode_2`.
- Updated the release build script and project documentation for the new
  firmware path.
- Exposed raw ESP8266 reset information in `/api/status` and the System
  diagnostics card to make future exception resets easier to decode.
- Added SoftAP diagnostics to `/api/status` and the System diagnostics card,
  including whether SoftAP is active, the SoftAP IP address, and the number of
  associated stations.
- Added reset reason and raw ESP8266 reset information to the Serial1/GPIO2
  boot log for crash diagnosis when Wi-Fi is unavailable.
- Added a Network-tab and Recovery-page action to forget saved Wi-Fi station
  credentials without deleting the uNode configuration.
- Recovery network startup now explicitly keeps saved Wi-Fi credentials instead
  of relying on the ESP8266 one-argument disconnect overload, which erases
  credentials.
- Added an initial RP2040 hardware-in-the-loop DMX input soak test with timing
  variation, random UART garbage, optional line-noise bursts, below-spec frame
  injection, valid-frame recovery checks, ArtDmx forwarding checks, and
  reboot/reset monitoring.

## [0.18.2] - 2026-06-27

### Changed

- The wrong-Port-Address status-bar warning now stays visible in the web
  interface for eight seconds after it is detected, making short recurring
  mismatch bursts readable.
- Changed the warning text to indicate a recent wrong-universe event rather
  than an always-current fault.

### Compatibility Notes

- No intentional breaking config change.
- This is a LittleFS web-asset behaviour fix.

## [0.18.1] - 2026-06-27

### Changed

- Changed the wrong-Port-Address status-bar warning from a historical counter
  warning to a live warning.
- The warning now clears when valid ArtDmx for the configured Port-Address is
  received after the wrong packet, or when the wrong packet is older than five
  seconds.
- Added the age of the last wrong Port-Address packet to Detailed Diagnostics.

### Compatibility Notes

- No intentional breaking config change.

## [0.18.0] - 2026-06-27

### Added

- Added a status-bar warning when ArtDmx packets are received for the wrong
  Port-Address in Art-Net-to-DMX mode.
- Added the last wrong ArtDmx Port-Address to `/api/status` and the Detailed
  Diagnostics page.

### Compatibility Notes

- No intentional breaking config change.
- The visible status-bar warning requires the matching LittleFS web files.

## [0.17.0] - 2026-06-27

### Added

- Added low-level Art-Net parser diagnostic counters for oversized packets,
  short packets, invalid Art-Net IDs, unsupported protocol versions, malformed
  packets, and unsupported opcodes.
- Added Art-Net runtime diagnostic counters for wrong Port-Address packets,
  direction drops, sequence drops, merge-lock drops, third merge-source drops,
  and ArtSync timeouts.
- Added an out-of-the-way Detailed Diagnostics page reachable from the System
  tab.
- Added the new diagnostic counters to `/api/status`.

### Compatibility Notes

- No intentional breaking config change.
- Detailed Diagnostics is a LittleFS web-asset feature and requires the
  matching web files.

## [0.16.0] - 2026-06-27

### Added

- Added ArtSync packet parsing and callback support to the Art-Net library.
- Added ArtSync buffering for Art-Net-to-DMX output: ArtDmx updates are held
  while sync mode is active and applied on ArtSync.
- Added the Art-Net four-second ArtSync timeout, after which output returns to
  normal asynchronous ArtDmx handling.
- Added ArtSync counters and state to `/api/status`.
- Added ArtSync packet count, last-sync age, and sync state to the dashboard.

### Compatibility Notes

- No intentional breaking config change.
- ArtSync only affects Art-Net-to-DMX mode. DMX-to-Art-Net transmission remains
  asynchronous.

## [0.15.0] - 2026-06-27

### Added

- Added explicit request-size limits for mutating JSON web endpoints.
- Added a configuration-upload size limit with HTTP `413` responses for
  oversized uploads.
- Added overrun protection for OTA upload streams that exceed their declared
  size.

### Changed

- Configuration uploads now include the file size in the browser request so the
  ESP8266 can reject oversized files before writing them.

### Compatibility Notes

- No intentional breaking config change.
- Configuration JSON uploads are limited to 8 KiB.
- DMX test JSON requests are limited to 3 KiB, enough for a full 512-slot value
  update.

## [0.14.0] - 2026-06-27

### Added

- Added a board-level hardware abstraction for RS-485 transceiver control.
- Added compile-time support for split RS-485 `/RE` and `DE` pins.
- Added switchable DMX bus termination control.
- Added persistent Hardware-tab termination modes: **Off**, **On**, and
  **Auto**.
- Added Hardware-tab status for split bus guarding, driver enable, receiver
  enable, and effective termination state.

### Changed

- The RS-485 pins are initialized in a passive state during boot before the DMX
  runtime applies the configured direction.
- Hardware termination is applied live when saved from the web interface and
  automatically follows direction changes in **Auto** mode.
- Configuration schema version increased to `2`.

### Compatibility Notes

- Existing schema `1` configurations are migrated automatically and default
  `terminationMode` to **Auto**.
- Split control defaults to GPIO5 as active-low `/RE` and GPIO12 as active-high
  `DE`.
- Switchable termination defaults to GPIO13 and can be disabled at compile time
  for legacy hardware.

## [0.13.0] - 2026-06-27

### Added

- Added a web-interface theme selector next to Login/Logout with **Auto**,
  **Light**, and **Dark** modes.
- Added browser-local theme persistence using `localStorage`.
- Added automatic theme updates when **Auto** is selected and the operating
  system/browser color-scheme preference changes.

### Changed

- Converted the main web stylesheet to theme variables for page, card, form,
  warning, monitor, and overlay colors.

### Compatibility Notes

- No intentional breaking config change.
- Theme selection is stored in the browser, not in `/config.json`.
- This is a LittleFS web-asset feature and requires the matching web files.

## [0.12.1] - 2026-06-27

### Fixed

- Restored the expected LED brightness workflow: moving the slider now acts as
  a temporary live preview, while only the normal Save action stores the value
  permanently.
- Reloading the web interface reapplies the persisted LED brightness so an
  unsaved preview value is discarded.

### Compatibility Notes

- No intentional breaking config change.
- This is a LittleFS web-asset fix; upload the matching web files to get the
  corrected slider behavior.

## [0.12.0] - 2026-06-27

### Added

- Added a browser-side connection watchdog for the web interface.
- Added an automatic reconnect overlay when regular status polling detects that
  the node is unavailable outside an intentional restart.
- Added automatic status, authentication, and configuration refresh after the
  browser reconnects to the node.

### Changed

- Reused the restart overlay as a general connection-state overlay with a
  dynamic title.
- Suppressed periodic Art-Net subscriber refreshes while the browser connection
  is known to be offline.

### Compatibility Notes

- No intentional breaking config change.
- The connection watchdog is implemented in the LittleFS web assets and
  requires the matching web files to be uploaded.

## [0.11.0] - 2026-06-27

### Added

- Added a dedicated Hardware tab.
- Added a global Locate button to the page header so local or Art-Net-triggered
  Locate state is visible from every web page.
- Added a Hardware-tab placeholder for future RS-485 bus guarding and
  switchable termination controls.

### Changed

- Moved LED brightness from the dashboard Hardware card to the new Hardware tab.

### Compatibility Notes

- No intentional breaking config change.
- The updated navigation and header Locate button require the matching
  LittleFS web files for this firmware version.

## [0.10.0] - 2026-06-27

### Added

- Added runtime diagnostics to `/api/status`.
- Added a System-tab diagnostics panel with free heap, minimum free heap,
  largest free heap block, heap fragmentation, reset reason, boot count,
  config schema version, and installed/expected web-asset version.

### Compatibility Notes

- No intentional breaking config change.
- The new diagnostics panel requires the matching LittleFS web files for this
  firmware version.

## [0.9.0] - 2026-06-27

### Added

- Added `configVersion` to `/config.json` and introduced configuration schema
  version `1`.
- Added automatic migration/persistence for configurations without a schema
  version.
- Added LittleFS web-asset version marker `/version.json`.
- Added firmware status fields for expected and installed web-asset versions.
- Added a dashboard warning when the installed LittleFS web files do not match
  the running firmware.
- Updated the release build script to generate `/version.json` before creating
  the LittleFS image.

### Compatibility Notes

- Existing configurations without `configVersion` are migrated automatically.
- No intentional breaking config change.
- Firmware-only updates may now show a web-asset mismatch warning until the
  matching LittleFS image is uploaded.

## [0.8.0] - 2026-06-26

### Added

- Added live application of web-saved Art-Net and DMX runtime settings without
  rebooting the ESP8266.
- Added JSON save responses that tell the web interface whether a restart is
  required.
- Added dynamic status-bar save button text: live-only changes show **Save**,
  network-affecting changes show **Save & Restart**.

### Changed

- Web changes to Art-Net Port Name, Long Name, direction, Net/Sub/Universe,
  failsafe mode, merge mode, legacy ArtPollReply mode, and LED brightness are
  now applied immediately after saving.
- Network, hostname, and authentication-affecting configuration changes still
  use the existing restart-and-reconnect flow.

### Compatibility Notes

- No intentional breaking config change.
- Existing external clients that only check the HTTP status of `/api/config`
  continue to work, but the success response is now JSON instead of plain
  `OK`.

## [0.7.0] - 2026-06-26

### Added

- Added ArtDmx two-source output merging for Art-Net-to-DMX mode.
- Added persistent Output Merge configuration with HTP and LTP modes.
- Added ArtAddress `AcMergeLtp0`, `AcMergeHtp0`, and `AcCancelMerge` support.
- Added ArtPollReply GoodOutputA merge-active and LTP-mode status reporting.

### Changed

- ArtDmx sources are tracked by sender IP and Physical field, allowing two
  controllers to share the same Port-Address.
- A stale merge source is removed after the Art-Net ten-second merge timeout;
  the remaining source continues to drive the DMX output.
- A third simultaneous ArtDmx source for the same Port-Address is ignored and
  logged instead of disrupting the active merge.
- After `AcCancelMerge`, the next ArtDmx sender takes control and packets from
  other sender IP addresses are discarded while that source remains active.

### Compatibility Notes

- No intentional breaking config change. Older configurations default to HTP.
- If all ArtDmx input disappears, uNode's existing output failsafe behaviour
  remains responsible for the final DMX output state.

## [0.6.0] - 2026-06-26

### Added

- Added ArtAddress `AcDirectionTx0` and `AcDirectionRx0` support for live Port 0
  direction switching.
- Added a DMX UART restart path that stops the active UART mode and starts the
  newly configured input or output mode without rebooting.

### Changed

- ArtAddress direction changes are stored persistently and immediately update
  ArtPollReply port direction.
- Switching to DMX input clears subscriber state and starts a fresh ArtPoll
  discovery cycle.

### Compatibility Notes

- No intentional breaking config change.

## [0.5.0] - 2026-06-26

### Added

- Added ArtIpProg and ArtIpProgReply support for remote DHCP/static IP,
  subnet-mask, and gateway programming.
- Added LXESP8266DMX receiver support for short physical DMX frames with one or
  more data slots.
- Added RX idle-timeout based DMX frame completion so compact frames do not
  depend on receiving a full 513-byte packet or a later break interrupt.

### Changed

- ArtIpProg network changes are validated, stored, acknowledged, and then
  applied by an automatic restart.
- DMX receiver minimum slot handling is now independent from the transmitter's
  24-slot timing minimum.

### Fixed

- Fixed physical DMX input rejecting valid short frames, such as compact
  six-channel desks that send only changed/implemented channels.
- Fixed UART receive handling so pending FIFO bytes are drained on timeout and
  break interrupts, not only when the FIFO-full threshold is reached.

### Compatibility Notes

- No intentional breaking config change.
- The recovery/AP address remains fixed at `2.0.0.1`; ArtIpProg affects the
  station/client network configuration.

## [0.4.0] - 2026-06-26

### Added

- Added optional web-interface write protection with a status-bar Login/Logout
  button.
- Added RAM-only browser session tokens for protected API calls.
- Added password configuration in the System tab; an empty password disables
  write protection.
- Added Recovery Mode password reset/clear field.
- Added server-side protection for configuration changes, restart, Locate,
  brightness changes, configuration upload/download, subscriber polling, DMX
  test override, failsafe-scene recording, firmware update, and LittleFS update.

### Changed

- Dashboard, status, configuration display, DMX monitor, and subscriber list
  remain readable without login.
- When write protection is active and the browser is not logged in, GUI controls
  that can change settings or output are disabled.

### Compatibility Notes

- No intentional breaking config change.
- Existing configs without `adminPasswordHash` continue to load with write
  protection disabled.
- Configuration downloads can include the stored password hash and are therefore
  protected when write protection is enabled.

## [0.3.0] - 2026-06-25

### Added

- Added a temporary four-channel DMX Test Desk with Start Address, dynamic
  channel labels, value readout, Blackout Visible, Full On Visible, and Release
  Override.
- Added a non-persistent DMX test override layer that falls back to the real
  Art-Net or physical DMX source after 10 seconds without test activity.
- Added incoming ArtDmx sequence tracking per sender and rejection of stale or
  duplicate sequenced packets. Sequence `0` remains accepted as sequencing
  disabled.
- Added semantic static IPv4 validation in firmware and the web interface,
  including subnet-mask shape, network/broadcast-address checks, and gateway
  relationship checks.
- Added compile-time Serial1 logging on UART1 TX / GPIO2 so debug output can run
  while UART0 remains available for DMX.
- Added release artifacts with versioned firmware, LittleFS image, and manifest
  files including hashes and flash-layout information.
- Added firmware, LittleFS, and recovery OTA update support for the explicit
  `4M1M` flash layout.
- Added browser-side automatic reconnect/reload after save, restart, and update
  operations.
- Added validated configuration upload/download flow.

### Changed

- Version handling now derives `FW_VERSION` from `FW_VERSION_MAJOR`,
  `FW_VERSION_MINOR`, and `FW_VERSION_PATCH` at compile time.
- ArtPollReply firmware version is derived from the same firmware version
  defines instead of a hard-coded value.
- Static web assets are served with no-cache headers to avoid stale UI files
  after LittleFS updates.
- Web interface language and labels are now consistently English.
- Network and Art-Net settings pages were reorganized into clearer sections.
- ArtDmx output from DMX input mode now uses subscriber discovery instead of a
  stored manual target/broadcast selector.
- DMX output updates are only written when the shared frame actually changes.

### Fixed

- Fixed restored configuration uploads being rejected incorrectly.
- Fixed soft LED WebSocket messages causing dashboard status fields to become
  `NaN` or `undefined`.
- Fixed Art-Net packet switch fall-through by adding missing `break`
  statements.
- Removed the obsolete always-true ArtPollReply broadcast condition.
- Fixed favicon, manifest, and image paths after moving assets into
  `data/images/`.
- Fixed UI mojibake risk by using HTML entities and JavaScript Unicode escapes
  for visible special characters.

### Compatibility Notes

- No intentional breaking config change in this release.
- Legacy Art-Net target settings are migrated away from the old target selector
  model when a configuration is loaded.
- Complete LittleFS uploads still replace the whole filesystem, including
  `/config.json`; download the configuration first if it should be preserved.

### Known Follow-ups

- Add explicit LittleFS/web-asset version metadata and warn when firmware and
  filesystem versions do not match.
- Formalize config schema versions and document migrations or breaking changes
  per release.

## [0.2.0] - 2026-06-25

### Notes

- Earlier active development baseline before the changelog was introduced.
- Major work already included Art-Net/DMX operation, web configuration,
  LED-status abstraction, failsafe output modes, OTA/recovery groundwork, and
  the initial English web interface.
