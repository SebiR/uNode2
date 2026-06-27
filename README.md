# uNode 2 Project

This repository is structured as a small multi-project workspace.

## Layout

```text
firmware/uNode_2/      ESP8266 Arduino sketch and LittleFS web assets
tests/                 Python host-side and integration tests
tools/                 Build, release, and test helper scripts
artifacts/             Generated release files
doxygen/               Generated API documentation
misc/                  Loose project assets and experiments
```

The ESP8266 firmware remains Arduino-IDE compatible: open
`firmware/uNode_2/uNode_2.ino` as the sketch. The sketch folder name and the
`.ino` file name intentionally match.

Future helper firmware, such as an RP2040 DMX analyzer/test fixture, can live
next to the ESP8266 firmware in its own folder, for example
`firmware/rp2040_dmx_tool/`.

## Common commands

Run the Python unit tests:

```powershell
.\tools\test.ps1
```

Build versioned firmware and LittleFS release artifacts:

```powershell
.\tools\build_release.ps1
```
