# uNode 2 Project

This repository is structured as a small multi-project workspace.

## Layout

```text
firmware/uNode_2/      ESP8266 Arduino sketch and LittleFS web assets
firmware/rp2040_dmx_tool/
                       RP2040 DMX analyzer / test sender firmware
libraries/uNodeArtNet/ Portable Arduino Art-Net protocol library
libraries/LXESP8266DMX/
                       Local ESP8266 UART DMX library fork used by uNode
tests/                 Python host-side and integration tests
tools/                 Build, release, and test helper scripts
artifacts/             Generated release files
doxygen/               Generated API documentation
misc/                  Loose project assets and experiments
```

The ESP8266 firmware remains Arduino-IDE compatible: open
`firmware/uNode_2/uNode_2.ino` as the sketch. The sketch folder name and the
`.ino` file name intentionally match. The reusable Art-Net implementation and
the maintained ESP8266 DMX fork are kept below `libraries/`. Install or link
`libraries/uNodeArtNet` and `libraries/LXESP8266DMX` into the Arduino
sketchbook's `libraries` directory when compiling directly from Arduino IDE.
The repository build script supplies the complete local library path
automatically and therefore does not depend on global copies.

The RP2040 DMX tool is intended as the hardware test fixture for future
DMX-level integration tests.

## Common commands

Run the Python unit tests:

```powershell
.\tools\test.ps1
```

Run integration tests against a real uNode. If no IP address is provided, the
runner discovers the node by sending ArtPoll on the available IPv4 interfaces:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration
```

Useful explicit-target variant:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test.ps1 -Integration -NodeIp 2.0.0.1
```

Build versioned firmware and LittleFS release artifacts:

```powershell
.\tools\build_release.ps1
```

The release script builds both supported hardware profiles and writes artifacts
without a build timestamp in the file name:

- `uNode-<version>-firmware.bin`
- `uNode-<version>-littlefs.bin`
- `uNode-<version>_legacy-firmware.bin`
- `uNode-<version>_legacy-littlefs.bin`
- `uNode-<version>-manifest.json`

Flash a generated release over UART:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1
```

The UART flash helper lists the release artifacts in `artifacts/release`, asks
for the target firmware profile, lists detected serial ports with VID/PID, and
then flashes firmware plus LittleFS at 512000 baud. The selected USB serial
adapter is remembered in `artifacts/flash_uart.settings.json` for the next run.

Useful variants:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1 -ListOnly
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1 -Port COM15
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1 -FirmwareOnly
powershell -ExecutionPolicy Bypass -File .\tools\flash_uart.ps1 -LittleFsOnly
```

Flash a generated release over OTA:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\flash_ota.ps1 -FirmwareOnly -NodeIp 2.0.0.1
powershell -ExecutionPolicy Bypass -File .\tools\flash_ota.ps1 -LittleFsOnly -NodeIp 2.0.0.1
```

OTA firmware and LittleFS uploads restart the node after each upload, so the
helper intentionally performs one update type per run. Use `-Password` when the
web/API password is enabled.
