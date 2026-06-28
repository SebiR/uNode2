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

## Notes

- Integration tests may change the node configuration temporarily. They try to
  restore the previous configuration afterwards.
- The live-configuration integration test currently changes Art-Net direction,
  Net, Sub-Net, and Universe, verifies `/api/status`, verifies ArtPollReply, and
  then restores the previous configuration.
- The ArtAddress integration test programs temporary Short/Long Names, enables
  Locate, verifies `/api/status` and ArtPollReply, disables Locate again, and
  then restores the previous configuration.
- The ArtSync integration test enables synchronous output mode, sends ArtDmx,
  verifies that output is pending, sends a second ArtSync, and verifies that the
  pending frame is flushed.
- The ArtIpProg integration test sends a safe enquiry, verifies ArtIpProgReply
  network fields, and checks that the node remains reachable afterwards.
- Parser diagnostics tests send malformed UDP/Art-Net packets and verify the
  counters for oversized packets, short packets, invalid IDs, unsupported
  protocol versions, malformed ArtDmx lengths, and unsupported opcodes.
- The PollReply bit tests verify direction-dependent PortTypes, SwIn/SwOut,
  GoodOutputA/B, Status1 indicator bits, Status2 capability/squawk bits, and
  Status3 failsafe bits.
- The DMX hardware-in-the-loop tests send ArtDmx to uNode, receive the real DMX
  output with the RP2040 analyzer, and compare channel values across low,
  middle, and high DMX channel ranges.
- The DMX hardware-in-the-loop tests also verify ArtSync buffering/flush on the
  real DMX output and all four output failsafe modes after Art-Net timeout:
  Hold, All-to-Zero, All-to-Full, and Failsafe Scene.
- The DMX input hardware-in-the-loop test uses the RP2040 as a physical DMX
  sender, advertises the Python test process as an Art-Net subscriber, and
  verifies that uNode forwards the received DMX slots as ArtDmx.
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
