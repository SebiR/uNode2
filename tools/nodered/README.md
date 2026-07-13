# uNode Node-RED Monitor

This optional, read-only dashboard polls `http://2.0.0.1/api/status` every five
seconds. It is intended for the Raspberry Pi test rig where Ethernet provides
SSH/Internet access and Wi-Fi is dedicated to the uNode access point.

Install or update the flow locally on the Node-RED host:

```bash
cd ~/uNode2
.venv/bin/python tools/nodered/install_dashboard.py
```

Open `http://printer.local:1880/unode/status`. The installer uses Node-RED's
single-flow Admin API and therefore leaves unrelated flows untouched.
