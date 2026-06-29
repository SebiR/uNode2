# uNode Test Suite

This directory contains the first Python-based tests for uNode.

The tests are split into two groups:

- `unit`: offline tests for byte-level Art-Net packet helpers and parsers.
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

Run integration tests against a real node:

```powershell
$env:UNODE_RUN_INTEGRATION = "1"
$env:UNODE_BASE_URL = "http://2.0.0.1"
$env:UNODE_IP = "2.0.0.1"
python -m pytest tests/integration
```

Or:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1
```

The PowerShell runner uses verbose pytest output for integration tests, so the
terminal shows each major hardware interaction while the tests run. At the end
it prints a compact test certificate and removes `.pytest_cache` /
`__pycache__` directories.

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

Run the host-only soak/stability test for a specific duration:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Path tests/integration/test_soak.py -SoakSeconds 600
```

Optional soak tuning:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Path tests/integration/test_soak.py -SoakSeconds 3600 -SoakInterval 1 -SoakGrace 8
```

Run the RP2040 hardware-in-the-loop DMX input soak with timing/fault injection:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Rp2040Port auto -Path tests/integration/test_dmx_soak_hil.py -DmxSoakSeconds 600
```

Capture Serial1/GPIO2 debug output in a second terminal while soak tests run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\serial_capture.ps1 -List
powershell -ExecutionPolicy Bypass -File .\tools\serial_capture.ps1 -Port COM8 -Output logs\soak-serial.log
```

## Notes

- Integration tests may change the node configuration temporarily. They try to
  restore the previous configuration afterwards.
- The host-only soak test repeatedly checks HTTP reachability, ArtPollReply
  reachability, reboot counters, reset diagnostics, heap health, ArtDmx,
  ArtSync, malformed Art-Net parser probes, and live runtime configuration
  changes. It is intentionally excluded from normal quick runs unless selected
  by path.
- The DMX hardware-in-the-loop soak test uses the RP2040 as a physical DMX
  sender, varies Break/MAB/baud/slot timing, injects below-spec/random frames,
  optionally injects random line-noise bursts when the RP2040 firmware supports
  the `noise` JSON command, and verifies that uNode recovers to valid DMX input
  and keeps forwarding ArtDmx without rebooting.
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
