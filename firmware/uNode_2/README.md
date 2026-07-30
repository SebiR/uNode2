# uNode ESP8266 Firmware

This directory is the self-contained PlatformIO project for the uNode firmware.
It can be opened directly in VS Code with the PlatformIO extension, while the
repository root remains the workspace for libraries, tests, deployment tools,
and the RP2040 fixture.

## Layout

```text
data/                 LittleFS web application and version marker
scripts/              PlatformIO/SCons build hooks
tools/                Firmware-specific release builder
platformio.ini        Board, dependency, and environment configuration
uNode_2.ino            Arduino-compatible sketch entry point
*.cpp / *.h            Firmware modules
```

The reusable `uNodeArtNet` and `LXESP8266DMX` libraries intentionally remain in
the repository-level `libraries/` directory. `platformio.ini` references that
directory using a relative path, so no globally installed copy is used.

## Build

From this directory:

```powershell
pio run
pio run -e legacy
pio run -e gpio_fix
pio run -e test
pio run -e legacy_test
pio run -e normal -t buildfs
```

From the repository root, add `-d firmware/uNode_2` to the same commands.

Generate the complete versioned release set from the repository root with:

```powershell
.\firmware\uNode_2\tools\build_release.ps1 -IncludeTestHarness
```

Generated firmware, ELF/map files, LittleFS images, and the SHA-256 manifest
are written to the repository-level `artifacts/release/` directory.

The `gpio_fix` environment is for the PCB revision whose ESP8266 symbol
swapped GPIO4 and GPIO5. It drives the WS2812 chain on GPIO5, RS-485 `/RE` on
GPIO4, and uses the board's `NEO_GRB` color order.

The sketch remains compatible with the Arduino IDE. When compiling it there,
make the repository-local libraries available to the Arduino sketchbook and
use the ESP8266 Generic board with the `4M1M` flash layout.
