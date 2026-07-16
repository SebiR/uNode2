# uNode 2 Project

This repository is structured as a small multi-project workspace.

## Layout

```text
firmware/uNode_2/      Self-contained ESP8266 PlatformIO/Arduino firmware
  platformio.ini       Pinned build environments and dependencies
  data/                LittleFS web assets
  scripts/             PlatformIO build hooks
  tools/               Firmware release builder
firmware/rp2040_dmx_tool/
                       RP2040 DMX analyzer / test sender firmware
libraries/uNodeArtNet/ Portable Arduino Art-Net protocol library
libraries/LXESP8266DMX/
                       Local ESP8266 UART DMX library fork used by uNode
tests/                 Python host-side and integration tests
tools/                 Host tests, deployment, and fixture helper scripts
artifacts/             Generated release files
doxygen/               Generated API documentation
misc/                  Loose project assets and experiments
```

The ESP8266 firmware is built with PlatformIO by default and remains
Arduino-IDE compatible: open
`firmware/uNode_2/uNode_2.ino` as the sketch. The sketch folder name and the
`.ino` file name intentionally match. The reusable Art-Net implementation and
the maintained ESP8266 DMX fork are kept below `libraries/`. Install or link
`libraries/uNodeArtNet` and `libraries/LXESP8266DMX` into the Arduino
sketchbook's `libraries` directory when compiling directly from Arduino IDE.
PlatformIO uses the repository-local libraries automatically and downloads the
pinned third-party dependencies declared in
`firmware/uNode_2/platformio.ini`.

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
.\firmware\uNode_2\tools\build_release.ps1
```

The release build requires PlatformIO Core 6.1.19. The script finds either a
`pio`/`platformio` command on `PATH` or the Core installed by the VS Code
PlatformIO extension below `~/.platformio/penv`. The ESP8266 platform and all
third-party Arduino libraries are version-pinned in the firmware-local
`platformio.ini`.

Open `firmware/uNode_2` as the PlatformIO project in VS Code to use its toolbar.
From the workspace root, equivalent command-line builds are:

```powershell
pio run -d .\firmware\uNode_2                         # current hardware
pio run -d .\firmware\uNode_2 -e legacy               # legacy hardware
pio run -d .\firmware\uNode_2 -e test                 # test-harness API
pio run -d .\firmware\uNode_2 -e legacy_test          # legacy test build
pio run -d .\firmware\uNode_2 -e normal -t buildfs    # LittleFS image
```

The default environment is `normal`. All environments use the ESP8266 Arduino
3.1.2 framework, the `4M1M` flash layout, DOUT flash mode, and a 512000 baud
upload speed.

Development/production-test firmware with the isolated Wi-Fi test harness is
built only by explicit request:

```powershell
.\firmware\uNode_2\tools\build_release.ps1 -IncludeTestHarness
```

The release script builds both supported hardware profiles and writes artifacts
without a build timestamp in the file name:

- `uNode-<version>-firmware.bin`
- `uNode-<version>-littlefs.bin`
- `uNode-<version>_legacy-firmware.bin`
- `uNode-<version>_legacy-littlefs.bin`
- `uNode-<version>-manifest.json`

The opt-in command additionally creates `_test` and `_legacy_test` firmware.
These binaries define `ENABLE_TEST_HARNESS_API=1`; regular artifacts do not.

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
