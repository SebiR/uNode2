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

Install or update the flow locally on the Node-RED host:

```bash
cd ~/uNode2
.venv/bin/python tools/nodered/install_dashboard.py
```

Open `http://printer.local:1880/unode/status`. The installer uses Node-RED's
single-flow Admin API and therefore leaves unrelated flows untouched. The
dashboard also tails `artifacts/test_reports/latest-run.log`, which is updated
live by `tools/test.sh` while pytest is running.

The same guarded entry point can be used from a shell:

```bash
tools/nodered/run_soak.sh host 3600
tools/nodered/run_soak.sh dmx 3600
tools/nodered/run_soak.sh status
```
