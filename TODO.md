# uNode Roadmap

This document tracks remaining functional, reliability, and protocol work. It
lists only open items; implemented behaviour is documented in `MANUAL.md`.

## Priority 1: OTA and Boot Recovery

- [x] Make the `4M1M` flash layout explicit in all build and release commands.
- [x] Generate versioned firmware and LittleFS images as release artifacts.
- [x] Add hashes and flash-layout information to a small release manifest.
- [x] Store a LittleFS/web-asset version marker and warn in the web UI when
      firmware and filesystem assets do not match.
- [x] Add HTTP firmware upload using the ESP8266 `U_FLASH` updater.
- [x] Add authentication to firmware and filesystem update endpoints.
- [x] Add complete LittleFS-image upload using the ESP8266 `U_FS` updater.
- [x] Warn that a LittleFS update replaces `/config.json` and offer a direct
      configuration download before starting the update.
- [x] Embed a minimal recovery page in firmware/PROGMEM so it does not depend
      on LittleFS.
- [x] Enter the recovery AP at `2.0.0.1` only when the hardware button is held
      during power-on or reset.
- [x] If LittleFS cannot be mounted during a normal boot, show a persistent
      fault indication and require a reboot with the recovery button held.
- [x] Provide firmware upload, LittleFS upload, restart, and factory-reset
      actions on the recovery page.
- [x] Validate image type, size, upload completion, and updater errors before
      rebooting.
- [x] Add update progress and automatic browser reconnection after reboot.

## Priority 2: Output Failsafe

- [x] Detect loss of valid ArtDmx for the configured Port-Address using the
      existing five-second activity timeout.
- [x] Add persistent failsafe modes: Hold, All to Zero, All to Full, and
      Failsafe Scene.
- [x] Add an action to record the current output frame as the failsafe scene.
- [x] Store and validate the 512-byte failsafe scene.
- [x] Implement the ArtAddress commands `AcFailHold`, `AcFailZero`,
      `AcFailFull`, `AcFailScene`, and `AcFailRecord`.
- [x] Advertise the selected mode and programmable-failsafe support in
      ArtPollReply `Status3`.
- [x] Show failsafe settings only in Art-Net-to-DMX mode.
- [x] Show active failsafe state in the dashboard and NodeReport diagnostics.

## Priority 3: Art-Net Configuration and Compliance

- [x] Add a runtime-selectable legacy ArtPollReply profile for older Art-Net 3
      discovery tools.
- [x] Implement ArtIpProg and ArtIpProgReply for IP, subnet mask, gateway, and DHCP
      configuration.
- [x] Complete ArtAddress programming for Net, Subnet, SwIn, and SwOut.
- [x] Implement supported ArtAddress port-direction commands.
- [x] Add incoming ArtDmx sequence tracking and reject stale or duplicate
      sequenced packets.
- [x] Implement two-source HTP and LTP merging.
- [x] Apply the specified ten-second timeout when one merge source disappears.
- [x] Implement `AcCancelMerge` and advertise merge state correctly.
- [x] Implement ArtSync buffering and the four-second return to asynchronous
      operation.
- [ ] Decide whether application-level ArtNzs support is required.
- [x] Report malformed packets, unsupported opcodes, wrong Port-Address drops,
      ArtDmx sequence drops, merge drops, and ArtSync timeouts in Detailed
      Diagnostics.
- [ ] Extend Detailed Diagnostics with dropped poll replies, subscriber
      overflow, and UDP transmission failures.

## Priority 3b: sACN / ANSI E1.31 Protocol Option

- [x] Add a hard live-data protocol selection between **Art-Net** and
      **sACN / ANSI E1.31** while keeping Art-Net management active.
- [x] Extend configuration storage with a live protocol mode.
- [x] Update the web UI with a Live Protocol selector and hide Art-Net
      subscriber/merge controls when sACN live data is selected.
- [x] Implement sACN Data Packet reception on UDP port 5568, including packet
      validation, source tracking by CID, sequence handling, priority handling,
      and timeout/failsafe integration.
- [x] Join the correct sACN multicast group for the configured Universe when
      receiving network-to-DMX data.
- [x] Implement DMX-to-sACN transmission with sequence numbers, source name,
      CID, priority, and periodic refresh while DMX input remains active.
- [ ] Add explicit user-configurable sACN Source Name, priority, and persistent
      CID/UUID instead of deriving them from existing node identity.
- [ ] Decide whether sACN Universe Discovery and Synchronization packets are
      required for the first implementation or should remain later additions.
- [x] Document that Art-Net remote configuration features such as ArtAddress and
      ArtIpProg remain Art-Net management features while sACN mode is selected
      for live data.

## Priority 4: DMX Test Page

- [x] Restructure the Network web page to match the updated Art-Net page
      layout, with clearer sections for Wi-Fi mode, hostname, DHCP/static
      selection, and compact static IPv4 fields.
- [x] Decide between a focused four-channel tester and an advanced console
      view. The preferred first step is the four-channel tester.
- [x] Make Start Address select the four controlled DMX channels.
- [x] Update fader labels when Start Address changes.
- [x] Implement Full On for the selected channels.
- [x] Implement Blackout for the selected channels.
- [x] Add one bulk API request for all test-channel values instead of sending
      one HTTP request per channel.
- [ ] Add an optional Art-Osc / TouchOSC remote-control input for the DMX Test
      override mode. First MVP scope: receive Art-Osc `AUT` messages on UDP
      port 7000, map `FADER_A`, `SWITCH_A`, `MACRO_A`, and optionally `XY_A`
      to temporary test override actions, and keep the existing override
      timeout/hold behaviour. Treat this as a test-mode remote, not as a full
      Art-Osc implementation.
- [ ] Optionally add a master fader.
- [x] Disable or hide test output in DMX-to-Art-Net mode, or add an explicit
      DMX-input override mode.
- [x] Keep the DMX monitor separate from test-output controls.
- [x] Add a temporary test override that falls back to the real Art-Net/DMX
      source after 10 seconds without test activity.

## Priority 5: Runtime Hardening and Diagnostics

- [x] Add a configuration schema version, keep older configs migratable where
      practical, and document intentional breaking changes in `CHANGELOG.md`.
- [x] Add a dedicated **Hardware** web tab for board-level settings and status,
      moving LED brightness there and keeping Locate globally visible in the
      page header.
- [x] Add compile-time hardware capability defines for RS-485 transceiver
      control instead of making the hardware revision user-selectable.
- [x] Support split RS-485 control on the new hardware with GPIO5 as active-low
      `/RE` and GPIO12 as active-high `DE`.
- [x] Support switchable DMX bus termination on the new hardware via
      SN74LVC1G66 controlled by GPIO13; keep it unavailable in legacy mode.
- [x] Add Hardware-tab termination control with modes **Off**, **On**, and
      **Auto**. Auto enables termination in DMX input mode and disables it in
      DMX output mode.
- [x] Keep split RS-485 guarding unavailable on legacy hardware where `/RE` and
      `DE` are tied together; hide the GUI controls or show them disabled with
      a clear "requires split DE/RE hardware" note.
- [x] Use safe RS-485 boot defaults on new hardware: `DE` pulled low and `/RE`
      pulled high so the MAX3485 is completely passive during reset, boot logs,
      and flashing.
- [ ] Add optional boot bus guarding for split-control hardware: listen briefly
      after boot before enabling DMX output, detect existing DMX activity, and
      warn, block output, or optionally switch to DMX input according to a stored
      Hardware-tab setting.
- [ ] Consider collision/echo diagnostics by enabling the receiver while
      transmitting on split-control hardware and comparing the observed bus
      state with transmitted data.
- [ ] Confirm the hardware-button GPIO and electrical wiring in the schematic.
- [x] Prefer GPIO14 with an active-low button to ground and `INPUT_PULLUP` so
      the button can safely be held during power-on or reset.
- [ ] Add a debounced, non-blocking button state machine without GPIO
      interrupts.
- [ ] Use a short press to toggle local Art-Net Locate indication.
- [x] Sample and debounce the button before LittleFS and normal services start;
      a held button enters a physically authorized recovery boot mode.
- [x] Keep Recovery AP and Factory Reset unavailable during normal operation.
- [x] Remove Factory Reset from the normal web interface and expose it only on
      the firmware-embedded recovery page.
- [x] Remove the automatic runtime Recovery AP after failed client reconnects;
      continue reconnecting and require a button-assisted reboot for recovery.
- [x] Keep AP and AP + Client modes available when they are explicitly selected
      in the stored configuration.
- [x] Add a Network-tab and Recovery-page action to forget saved Wi-Fi station
      credentials without performing a full factory reset.
- [x] Expose the current recovery boot mode in diagnostics.
- [ ] Use a distinctive LED pattern for recovery boot.
- [x] Replace the current `DBG_PRINT` macros with a central logging layer.
- [x] Add compile-time verbosity levels: Off, Error, Warning, Info, Debug, and
      Trace.
- [x] Prefix log lines consistently with timestamp, severity, and module tags
      such as `BOOT`, `CFG`, `NET`, `ARTNET`, `DMX`, `WEB`, and `WS`.
- [ ] Compile messages above the selected verbosity completely out of release
      builds.
- [x] Separate the serial-logging switch from DMX feature selection and make
      Serial1/GPIO2 the default debug TX path while keeping UART0-DMX active.
- [x] Decide whether serial logging disables all physical DMX handling or only
      UART0 DMX output; UART0 logging is now an explicit special build mode.
- [x] Keep ISR paths free of serial output and rate-limit packet/frame-level
      Trace messages.
- [x] Remove sensitive values such as the generated access-point password from
      normal log levels.
- [x] Give each subsystem consistent lifecycle, state-change, warning, and
      error coverage without logging every packet at Info level.
- [ ] Optionally allow runtime verbosity reduction while keeping the compiled
      maximum controlled by the build configuration.
- [ ] Reduce the current high IRAM usage and preserve headroom for OTA and
      protocol additions.
- [ ] Reduce repeated `String` and dynamic JSON allocation in status and
      WebSocket updates.
- [x] Add free heap, largest free block, minimum free heap, reset reason, and
      boot count to diagnostics.
- [x] Add a browser-side connection watchdog that detects a missing node,
      shows reconnect status, and refreshes status/configuration after the node
      returns.
- [x] Add browser-local Auto/Light/Dark theme selection to the web interface.
- [x] Add upload and request-size limits to all web endpoints.
- [x] Protect configuration, restart, reset, and update endpoints with
      authentication.
- [x] Replace firmware-side blocking restart delays with a scheduled restart.
- [x] Validate static network settings semantically, including subnet masks
      and address relationships.
- [x] Clamp the copied physical DMX slot count defensively before clearing the
      remainder of the frame buffer.
- [x] Return a proper error when the root web asset is missing.
- [ ] Expose Art-Net socket bind retries and network recovery state clearly.
- [x] Expose raw ESP8266 reset information in diagnostics so exception resets
      include decoder-friendly details such as EPC and exception address.
- [x] Expose SoftAP health diagnostics, including active state, SoftAP IP, and
      associated station count.
- [x] Print reset reason and raw ESP8266 reset information on the Serial1/GPIO2
      debug interface during boot.
- [x] Apply web-saved Art-Net/DMX runtime settings live without rebooting when
      no network or hostname setting changed.
- [ ] Add optional capture/printing guidance for serial exception stack traces
      so rare crashes can be decoded after soak or HIL runs.
- [ ] Add AP-mode health recovery for cases where the SoftAP remains visible
      but stops accepting client associations.

## Priority 6: Verification and Release Quality

- [x] Update LXESP8266DMX input handling to accept short DMX frames with one
      or more data slots; its current receive path rejects frames below the
      24-slot transmitter minimum.
- [x] Separate the DMX transmitter minimum from the receiver minimum instead
      of using `DMX_MIN_SLOTS` for both directions.
- [x] Complete short physical DMX frames on RX idle timeout instead of relying
      only on 513 received bytes or a following break interrupt.
- [x] Verify by code path and compile that the receive callback and
      `copyFrame()` report the exact slot
      count for short frames.
- [ ] Test 1-, 6-, 23-, 24-, 25-, and 512-slot input frames with the RP2040
      fixture and confirm that stale channels above the received length are
      cleared by uNode.
- [ ] Keep short-frame DMX output as a separate decision because the sender
      must still satisfy minimum break-to-break timing.
- [x] Build an RP2040-based hardware-in-the-loop DMX test fixture.
- [x] Use PIO to generate configurable DMX break, mark-after-break, slot timing,
      slot count, frame rate, and channel values.
- [x] Use a separate PIO receive path to capture complete DMX frames and
      measure timing, jitter, framing errors, and channel data from uNode.
- [x] Add initial controlled DMX-input fault injection for invalid timing,
      below-spec frames, random UART garbage, and line-noise bursts.
- [ ] Extend controlled fault injection with explicit missing frames, truncated
      frames, and deliberate signal loss.
- [x] Define a small versioned USB-serial command protocol with machine-readable
      `OK`, `ERROR`, measurement, and frame responses.
- [x] Add commands for fixture identity, mode selection, transmitter settings,
      frame data, capture control, statistics, and reset.
- [ ] Add switchable RS-485 direction and termination to the fixture hardware;
      consider galvanic isolation for robust bench use.
- [x] Add host-side hardware-in-the-loop tests that coordinate the RP2040,
      uNode HTTP API, and Art-Net UDP traffic.
- [x] Verify both DMX-to-Art-Net and Art-Net-to-DMX directions automatically.
- [x] Cover signal-loss failsafe, refresh intervals, channel mapping, frame
      length, and direction changes in the hardware test suite.
- [x] Add RP2040 DMX analyzer/test-fixture firmware in a dedicated project
      folder, for example `firmware/rp2040_dmx_tool`.
- [x] Add a Python serial client for the RP2040 DMX tool JSONL protocol.
- [x] Add hardware-in-the-loop tests that verify uNode Art-Net-to-DMX output
      with the RP2040 analyzer.
- [x] Add hardware-in-the-loop coverage for sparse DMX channel mapping, ArtSync
      flush and timeout flush to real DMX output, and Art-Net timeout failsafe
      zero output.
- [x] Add hardware-in-the-loop coverage for all output failsafe modes: Hold,
      All to Zero, All to Full, and Failsafe Scene.
- [x] Add hardware-in-the-loop tests that verify uNode DMX-to-Art-Net input
      with the RP2040 sender.
- [x] Add full 512-slot hardware-in-the-loop coverage in both DMX directions
      to catch off-by-one errors at channel 512.
- [x] Add hardware-in-the-loop DMX output timing coverage for Break,
      Mark-After-Break, full-frame period, slot count, and baud estimate.
- [x] Add initial host-side tests for Art-Net packet parsing and packet
      generation.
- [x] Add live hardware integration coverage for REST configuration updates,
      `/api/status`, and matching ArtPollReply Port-Address fields.
- [x] Add host-side ArtAddress integration coverage for Short/Long Name
      programming, Locate, `/api/status`, and ArtPollReply.
- [x] Add host-side ArtSync integration coverage for synchronous ArtDmx
      buffering, explicit flush, timeout flush, and return to asynchronous
      output.
- [x] Add safe host-side ArtIpProg enquiry coverage without changing the node
      IP address.
- [x] Add host-side PollReply bit coverage for port direction, SwIn/SwOut,
      GoodOutput, Status1, Status2, Status3, Locate, merge mode, and failsafe.
- [ ] Extend host-side Art-Net tests for destructive/opt-in ArtIpProg edge
      cases and additional PollReply fields.
- [x] Add malformed and truncated UDP-packet tests for oversized packets,
      short packets, invalid Art-Net IDs, unsupported protocol versions,
      malformed ArtDmx lengths, and unsupported opcodes.
- [x] Add ArtDmx sequencing tests for duplicate drops, out-of-order drops,
      sequence `0` disable/reset behaviour, and `255 -> 1` wraparound.
- [ ] Add configuration import, migration, and interrupted-write tests.
- [ ] Test `millis()` rollover behaviour for all timeout state machines.
- [ ] Run long-duration soak tests with DMX traffic, WebSocket clients, Wi-Fi
      interruptions, and repeated controller discovery.
- [x] Add an initial host-only soak test for repeated HTTP/API reachability,
      ArtPollReply reachability, ArtDmx, ArtSync, malformed parser probes,
      runtime direction/failsafe/merge changes, reboot detection, reset-info
      reporting, and heap monitoring.
- [x] Add a hardware-in-the-loop soak mode with RP2040 DMX input/output traffic
      and timing variation during long runs.
- [x] Add an initial RP2040 hardware-in-the-loop DMX input soak with timing
      variation, random UART garbage, optional line-noise bursts, below-spec
      frame injection, valid-frame recovery checks, ArtDmx forwarding checks,
      and reboot/reset monitoring.
- [ ] Extend the RP2040 soak with simultaneous Art-Net output/DMX output
      monitoring and longer mixed-direction runs.
- [ ] Test power loss during firmware, LittleFS, and configuration updates.
- [ ] Add a Doxygen configuration and generated API-documentation workflow.
- [ ] Keep `MANUAL.md` and this roadmap synchronized with each release.

## Low-Priority Art-Net Nice-to-Haves

- [ ] Consider implementing `OpInput` / ArtInput as non-persistent runtime
      control for enabling or disabling DMX-to-Art-Net input transmission.
- [ ] Consider ArtDiagData output and the existing PriorityCodes only if
      external Art-Net diagnostic consumers become useful; the web diagnostics
      page is the preferred diagnostics interface for now.

## Deliberate Scope Decisions

- The web interface uses English only; a localization framework is currently
  out of scope.
- A complete LittleFS update may reset the configuration. Users are expected
  to download the configuration first when preservation is required.
- The recovery and configuration access-point address remains `2.0.0.1` by
  design.
- HTTP OTA is preferred over implementing the ArtFirmwareMaster transfer
  protocol.
