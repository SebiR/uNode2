# uNode Test Suite

This directory contains the first Python-based tests for uNode.

The tests are split into two groups:

- `unit`: offline tests for byte-level Art-Net packet helpers and parsers.
- `integration`: opt-in tests against a real uNode on the network.

## Requirements

Python 3.12 and `pytest` are expected. The helper code itself uses only the
Python standard library.

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
terminal shows each major hardware interaction while the tests run.

If the web interface is password-protected, also set:

```powershell
$env:UNODE_PASSWORD = "your-password"
```

Or pass it to the runner:

```powershell
.\tools\test.ps1 -Integration -NodeIp 2.0.0.1 -Password "your-password"
```

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
- The PollReply bit tests verify direction-dependent PortTypes, SwIn/SwOut,
  GoodOutputA/B, Status1 indicator bits, Status2 capability/squawk bits, and
  Status3 failsafe bits.
- ArtPollReply tests bind UDP port `6454`, because uNode sends replies to the
  standard Art-Net port. Close other Art-Net software if the port is already in
  use.
- These helpers intentionally stay byte-oriented. They are test fixtures, not a
  second full Art-Net implementation.
