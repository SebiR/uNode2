# uNode Test Suite

This directory contains the first Python-based tests for uNode.

The tests are split into two groups:

- `unit`: offline tests for byte-level Art-Net packet helpers/parsers and
  release helper consistency.
- `integration`: opt-in tests against a real uNode on the network.

## Requirements

Python 3.12, `pytest`, and `pyserial` are expected.

Run offline tests:

```powershell
python -m pytest tests/unit
```

Or use the PowerShell test runner:

```powershell
.\tools\test.ps1
```

On Linux or Raspberry Pi, prepare a virtual environment once and use the
equivalent shell runner:

```bash
bash tools/bootstrap_test_host.sh
bash tools/test.sh
```

Run integration tests against a real node:

```powershell
$env:UNODE_RUN_INTEGRATION = "1"
$env:UNODE_BASE_URL = "http://2.0.0.1"
$env:UNODE_IP = "2.0.0.1"
python -m pytest tests/integration
```

Or:

```powershell
.\tools\test.ps1 -Integration
```

Linux/Raspberry Pi, including RP2040 auto-detection:

```bash
bash tools/test.sh --integration --rp2040-port auto
```

The production fixture can expose the uNode button and reset input through the
RP2040 AUX GPIOs. For example, with reset wired to GPIO7:

```bash
bash tools/test.sh --integration --rp2040-port auto --reset-gpio 7 \
  --path tests/integration/test_rp2040_gpio_hil.py
```

The reset test records time-to-API, time-to-ArtPollReply, and time-to-working
physical DMX output in the JSON test report.

The Linux discovery helper reads every active IPv4 interface through
`iproute2`. A Raspberry Pi can therefore keep Internet/SSH on Ethernet while
its Wi-Fi interface is connected directly to the uNode access point.

For a dedicated Raspberry Pi test rig, keep the uNode Wi-Fi connection away
from the default route and pin the directly connected `2.0.0.0/24` network to
`wlan0`. This prevents NetworkManager from sending uNode traffic through the
Ethernet router after the access point briefly disappears during a restart:

```bash
sudo nmcli connection modify "uNode_CHIPID" \
  connection.interface-name wlan0 \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.never-default yes \
  ipv4.routes "2.0.0.0/24"
sudo nmcli connection up "uNode_CHIPID"
```

Disable auto-connect on unrelated Wi-Fi profiles when `wlan0` is reserved for
the test fixture. Ethernet continues to provide SSH and Internet access.

When `-NodeIp` and `-BaseUrl` are omitted, the PowerShell runner sends ArtPoll
on the available IPv4 interfaces and uses the first responding uNode. If no
node is discovered, it falls back to the AP/recovery default `2.0.0.1`.

You can still target a node explicitly:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1
```

The PowerShell runner uses verbose pytest output for integration tests, so the
terminal shows each major hardware interaction while the tests run. At the end
it prints a compact test certificate and removes `.pytest_cache` /
`__pycache__` directories.

Each test run also writes a structured JSON report to
`artifacts/test_reports/`. The report contains node identity, firmware version,
summary counts, mapped production-test group/title labels, and raw pytest
node IDs. Use `-ReportJson path\to\report.json` to choose a specific output
path. Human-readable labels are stored in `tests/report_mapping.en.json`; a
localized mapping can be added later without renaming the actual tests.

Generate an HTML/PDF production-test certificate from the newest JSON report:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\certificate.ps1
```

Or choose a specific report:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\certificate.ps1 -Report artifacts\test_reports\unode-DCAC4E-test-report-20260701-150230Z.json
```

Generated certificates are written to `artifacts/certificates/`. PDF rendering
uses a local Chrome/Edge installation when available; the HTML file is always
generated.

If the web interface is password-protected, also set:

```powershell
$env:UNODE_PASSWORD = "your-password"
```

Or pass it to the runner:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Password "your-password"
```

Run hardware-in-the-loop DMX tests with an RP2040 DMX tool connected by USB:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port COM7
```

Or auto-detect a single connected RP2040 USB serial port:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto
```

The RP2040 tests are skipped unless `UNODE_RP2040_PORT` or `-Rp2040Port` is
provided.

Run the host-only network-output soak/stability tests for a specific duration.
This runs Art-Net -> DMX and sACN -> DMX profiles:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Path tests/integration/test_soak.py -SoakSeconds 600
```

Optional soak tuning:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Path tests/integration/test_soak.py -SoakSeconds 3600 -SoakInterval 1 -SoakGrace 8
```

Run the RP2040 hardware-in-the-loop DMX input soak with timing/fault injection.
This runs DMX -> Art-Net and DMX -> sACN profiles:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto -Path tests/integration/test_dmx_soak_hil.py -DmxSoakSeconds 600
```

Run the RP2040 hardware-in-the-loop latency profile. This measures practical
end-to-end latency for Art-Net -> DMX, sACN -> DMX, DMX -> Art-Net, and
DMX -> sACN on the currently active Wi-Fi setup, so run it once in AP mode and
once in client mode if you want to compare both. The network-to-DMX latency
profiles require RP2040 DMX tool firmware with the JSON `wait` command:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto -Path tests/integration/test_latency_hil.py -LatencySamples 50
```

Run the RP2040 hardware-in-the-loop dropout profile. This sends unique,
moderate-rate updates and verifies that every network update reaches the real
DMX output, and every physical DMX change reaches the network output:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto -Path tests/integration/test_dropout_hil.py -DropoutSamples 100
```

Optional dropout tuning:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto -Path tests/integration/test_dropout_hil.py -DropoutSamples 200 -DropoutInterval 0.05 -DropoutTimeout 2.0 -DropoutAllowedLosses 0
```

Capture Serial1/GPIO2 debug output in a second terminal while soak tests run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\serial_capture.ps1 -List
powershell -ExecutionPolicy Bypass -File .\tools\serial_capture.ps1 -Port COM8 -Output logs\soak-serial.log
```

## Notes

- Integration tests may change the node configuration temporarily. They try to
  restore the previous configuration afterwards.
- Offline release-helper tests verify that `data/version.json` matches the
  firmware/config schema defines, that the UART flash helper lists normal and
  legacy release artifacts in the expected order, and that the OTA flash helper
  dry-run path targets the expected update endpoint.
- The Bus Guarding integration test verifies that `busGuardMode` is persisted,
  exposed through `/api/status`, and correctly marked as restart-required.
- The Bus Guarding hardware-in-the-loop test uses the RP2040 as a physical DMX
  sender during an API-triggered node restart and verifies that boot-time Bus
  Guarding switches the node from DMX output to DMX input when valid DMX is
  already present on the RS-485 bus.
- The RP2040 AUX GPIO hardware-in-the-loop test verifies the tester's JSON GPIO
  commands. If `UNODE_BUTTON_GPIO_PIN` is set to the RP2040 GPIO wired to the
  uNode active-low button input, additional tests press the local button and
  verify that short press toggles Locate and long press toggles status LED mute.
  If `UNODE_RESET_GPIO_PIN` is set to the GPIO wired to the active-low reset
  input, another optional test pulses reset and verifies that the boot counter
  increases.
- The restart persistence integration test stores representative runtime and
  hardware settings, restarts the node through `/api/restart`, and verifies the
  restored configuration through `/api/config`, `/api/status`, and ArtPollReply.
- The host-only soak tests repeatedly check HTTP reachability, ArtPollReply
  reachability, reboot counters, reset diagnostics, heap health, ArtDmx/sACN
  output input traffic, ArtSync, malformed Art-Net/sACN parser probes, and live
  runtime configuration changes. They are intentionally excluded from normal
  quick runs unless selected by path.
- The DMX hardware-in-the-loop soak test uses the RP2040 as a physical DMX
  sender, varies Break/MAB/baud/slot timing, injects below-spec/random frames,
  optionally injects random line-noise bursts when the RP2040 firmware supports
  the `noise` JSON command, and verifies that uNode recovers to valid DMX input
  and keeps forwarding ArtDmx or sACN without rebooting.
- The live-configuration integration test currently changes Art-Net direction,
  Net, Sub-Net, and Universe, verifies `/api/status`, verifies ArtPollReply, and
  then restores the previous configuration.
- The ArtAddress integration test programs temporary Short/Long Names, enables
  Locate, verifies `/api/status` and ArtPollReply, disables Locate again, and
  then restores the previous configuration.
- The ArtSync integration tests enable synchronous output mode, send ArtDmx,
  verify that output is pending, flush with a second ArtSync, and verify that
  the four-second ArtSync timeout flushes pending data and returns to
  asynchronous output.
- The ArtIpProg integration test sends a safe enquiry, verifies ArtIpProgReply
  network fields, and checks that the node remains reachable afterwards.
- The auth protection test temporarily enables the web/API password, verifies
  that read-only status endpoints remain reachable, verifies that mutating API
  endpoints reject anonymous requests, checks login failure/success, and then
  restores the original authentication state.
- Parser diagnostics tests send malformed UDP/Art-Net packets and verify the
  counters for oversized packets, short packets, invalid IDs, unsupported
  protocol versions, malformed ArtDmx lengths, and unsupported opcodes.
- ArtDmx sequencing tests verify duplicate/out-of-order packet drops, sequence
  `0` as sequencing-disabled reset, and `255 -> 1` wraparound acceptance.
- The PollReply bit tests verify direction-dependent PortTypes, SwIn/SwOut,
  GoodOutputA/B, Status1 indicator bits, Status2 capability/squawk bits, and
  Status3 failsafe bits.
- The DMX hardware-in-the-loop tests send ArtDmx to uNode, receive the real DMX
  output with the RP2040 analyzer, and compare channel values across low,
  middle, and high DMX channel ranges.
- The DMX hardware-in-the-loop tests also verify Art-Net merge behaviour by
  sending two ArtDmx sources from one test host with different Physical fields:
  HTP must output the per-channel maximum, LTP must follow the latest source,
  stale sources must expire, third sources must be rejected, ArtAddress
  `AcCancelMerge` must lock output to the next source, and `/api/status` must
  report the active Physical sources.
- The latency hardware-in-the-loop profile is a practical comparison test, not
  a microsecond-accurate lab measurement. Network-to-DMX measurements include
  host UDP send, Wi-Fi, uNode processing, and DMX output scheduling. DMX-to-
  network measurements also include the USB command used to trigger a single
  RP2040 DMX frame, which makes them most useful for comparing AP/client mode
  or Art-Net/sACN behaviour on the same bench setup. Longer DMX-to-Art-Net
  profiles refresh the Python test subscriber periodically so uNode does not
  expire it from the Art-Net subscriber list during the test.
- The dropout hardware-in-the-loop profile checks lossless update delivery at
  a moderate rate. It intentionally does not try to prove that every overly
  fast network packet becomes a separate physical DMX frame; at rates above
  the DMX output frame rate, the correct behaviour may be to output the most
  recent state and skip intermediate values.
- The DMX hardware-in-the-loop tests also verify ArtSync buffering/flush and
  ArtSync timeout flush on the real DMX output, plus all four output failsafe
  modes after Art-Net timeout: Hold, All-to-Zero, All-to-Full, and Failsafe
  Scene. The Failsafe Scene test records and verifies all 512 DMX slots.
- The DMX input hardware-in-the-loop tests use the RP2040 as a physical DMX
  sender, advertise the Python test process as an Art-Net subscriber, and
  verify that uNode forwards both short and full received DMX frames as ArtDmx.
- Full-frame DMX tests verify all 512 slots in both directions, including the
  final slots near channel 512.
- The DMX output timing test measures Break, Mark-After-Break, frame/data time,
  slot count, and estimated baud rate with the RP2040 analyzer and prints
  actual values, accepted windows, and percentage deviation from nominal timing.
- ArtPollReply tests bind UDP port `6454`, because uNode sends replies to the
  standard Art-Net port. Close other Art-Net software if the port is already in
  use.
- These helpers intentionally stay byte-oriented. They are test fixtures, not a
  second full Art-Net implementation.
