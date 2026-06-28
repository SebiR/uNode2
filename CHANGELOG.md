# Changelog

All notable user-facing and compatibility-relevant changes are documented here.
Newest versions are listed first.

The project is still below `1.0.0`. Minor versions mark completed feature
blocks, while patch versions are reserved for focused bug-fix or hotfix builds.

Breaking changes, config migrations, and compatibility notes must be called out
explicitly in each release entry.

## [Unreleased]

## [0.19.3] - 2026-06-28

### Added

- Added DMX Test patterns for Channel Chase and Find Address with configurable
  scan range, speed, pause/resume, previous/next, and stop controls.
- Added a non-persistent DMX test option to disable the local override timeout
  until the next node restart.

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
