# RP2040 DMX Tool

DMX analyzer and test sender firmware for uNode hardware-in-the-loop tests.

The tool is designed as a small USB-serial controlled DMX instrument. It can
still be used manually from a terminal, but the primary automation interface is
JSON Lines: one JSON object per command, one JSON object per response.

## Hardware

Default pins are intended for Raspberry Pi Pico / Arduino-Pico `Serial1`:

- `GPIO0`: DMX TX to RS-485 driver input.
- `GPIO1`: DMX RX from RS-485 receiver output.
- optional `DMX_DIR_PIN`: RS-485 DE/!RE direction control, disabled by default.
- `GPIO6`, `GPIO7`, `GPIO8`: auxiliary test GPIOs for jig control such as
  pulling the uNode button input low or toggling an external reset circuit.
- `GPIO16`: onboard WS2812 status LED on the Waveshare RP2040-Zero.

Adjust the pin definitions in `DmxToolConfig.h` if your transceiver uses
different wiring. The pin macros are guarded with `#ifndef`, so they can also
be overridden by compiler flags.

If `DMX_DIR_PIN` is set to a valid GPIO, the tool drives the bus transceiver
automatically:

- RX mode: `DMX_DIR_RX_LEVEL`
- TX mode and line-noise generation: `DMX_DIR_TX_LEVEL`
- Idle/stop: direction pin, TX, and RX are released as inputs

For a common tied `DE` + `!RE` transceiver input, use the defaults
`DMX_DIR_TX_LEVEL HIGH` and `DMX_DIR_RX_LEVEL LOW`.

## Dependencies

- PlatformIO Core 6.1.19.
- Arduino-Pico core 5.6.0 for RP2040 boards.
- ArduinoJson 7.4.3.
- Adafruit NeoPixel 1.15.2. Its RP2040 backend uses PIO for status LED output.

The PlatformIO project pins the RP2040 platform, Arduino-Pico core, and both
libraries in `platformio.ini`. It deliberately uses the Earle Philhower core
instead of the Mbed Arduino core because the DMX implementation relies on its
RP2040 UART and PIO APIs.

## Build and upload

Open this directory as the PlatformIO project in VS Code, or build it from the
repository root:

```powershell
pio run -d .\firmware\rp2040_dmx_tool
```

Upload to a connected Waveshare RP2040-Zero and open the JSONL serial monitor:

```powershell
pio run -d .\firmware\rp2040_dmx_tool -t upload
pio device monitor -d .\firmware\rp2040_dmx_tool
```

The generated UF2 file is
`.pio/build/tester/firmware.uf2` below this project directory. The existing
Arduino sketch layout remains Arduino-IDE compatible; PlatformIO compiles the
matching `rp2040_dmx_tool.ino` directly from the project root.

## Status LED

The onboard WS2812 provides a compact view of tester activity:

- white briefly after boot: LED self-test and initialization
- slowly pulsing blue: idle; DMX and auxiliary pins are released
- dim cyan with green activity pulses: RX analyzer mode and received frames
- dim amber: TX mode is selected but continuous output is stopped
- amber activity pulses: continuous DMX transmission
- red briefly: invalid JSON command or command parameter

LED updates are deferred while an incoming DMX frame is being measured. Set
`STATUS_LED_PIN=-1` at compile time to disable the status pixel.

## Serial Protocol

Open USB serial at `115200` baud. Every machine-readable command and response
is one JSON object terminated by `\n`.

The firmware prints a ready event after boot:

```json
{"ok":true,"event":"ready","tool":"rp2040_dmx_tool","fw":"0.3.2","protocol":"jsonl"}
```

After boot the DMX UART is idle and the DMX TX/RX pins are high impedance.
The auxiliary GPIOs are also released as inputs. This keeps directly connected
UARTs and test points passive until a command explicitly drives them.

Useful commands:

```json
{"cmd":"ping"}
{"cmd":"mode","value":"rx"}
{"cmd":"mode","value":"tx"}
{"cmd":"mode","value":"idle"}
{"cmd":"get","target":"stats"}
{"cmd":"get","target":"frame","start":1,"count":16}
{"cmd":"wait","target":"frame","start":1,"values":[10,20,30,40],"timeoutMs":1500}
{"cmd":"set","target":"slots","value":512}
{"cmd":"set","target":"channel","channel":1,"value":255}
{"cmd":"set","target":"channels","values":{"1":255,"2":128,"3":0}}
{"cmd":"set","target":"frame","slots":6,"values":[0,93,112,173,148,93]}
{"cmd":"set","target":"timing","breakUs":176,"mabUs":16,"mbbUs":0,"interSlotUs":0,"baud":250000,"fps":40}
{"cmd":"set","target":"pattern","value":"ramp"}
{"cmd":"tx","action":"start"}
{"cmd":"tx","action":"stop"}
{"cmd":"tx","action":"send"}
{"cmd":"noise","durationMs":100,"minPulseUs":2,"maxPulseUs":200}
{"cmd":"gpio","action":"read","pin":6}
{"cmd":"gpio","action":"input","pin":6,"pullup":true}
{"cmd":"gpio","action":"write","pin":6,"value":0}
{"cmd":"gpio","action":"pulse","pin":6,"value":0,"durationMs":300,"release":true}
{"cmd":"gpio","action":"release","pin":6}
{"cmd":"clear","target":"stats"}
```

Example responses:

```json
{"ok":true,"type":"pong","fw":"0.3.2","mode":"RX analyzer","auxGpioPins":[6,7,8]}
```

`gpio read` reports the current pin level without changing the pin mode. Use
`gpio input` or `gpio release` when the pin should become high impedance before
reading an externally driven signal.

```json
{"ok":true,"type":"frame","mode":"RX analyzer","seq":123,"startCode":0,"slots":6,"start":1,"count":6,"values":[0,93,112,173,148,93]}
```

The `wait` command switches to RX analyzer mode if needed, waits locally on
the RP2040 until a newly received DMX frame matches the requested channel
values, and returns the elapsed time measured by the RP2040. This is used by
the latency HIL tests to avoid USB polling jitter:

```json
{"ok":true,"type":"wait","matched":true,"elapsedUs":42150,"framesSeen":2,"startCode":0,"slots":512,"start":1,"count":4,"values":[10,20,30,40]}
```

Errors are also JSON:

```json
{"ok":false,"error":"invalid_channel","message":"Channel must be 1..512"}
```

## Legacy terminal commands

Plain-text commands from the previous terminal UI are still available for manual
use:

```text
help
rx
tx
stats
reset
view on
view off
window 1 64
slots 6
set 1 255
pattern chase
break 92
mab 12
fps 40
inter 100
start
stop
send
```

The live table is disabled by default so automated tests receive only JSON
unless it is explicitly enabled with `view on`.

`idle`, `stop`, and one-shot `send` release the DMX UART afterwards and return
the DMX TX/RX pins to high impedance.

## DMX timing baseline

DMX512-A uses 250 kBd asynchronous serial data with 8 data bits, no parity, and
two stop bits. A packet starts with Break, Mark-After-Break, start code, and up
to 512 data slots.

The sender defaults are deliberately conservative:

- Break: `176 us`
- Mark-After-Break: `16 us`
- Baud: `250000`
- Slots: `24`

For receiver hardening tests, useful edge cases are:

- very short packets such as `slots 6`;
- minimum legal sender timings such as `break 92` and `mab 12`;
- slightly below-minimum timings to confirm rejection/robustness;
- random line-noise bursts that simulate cable plug/unplug transients;
- long inter-slot gaps via `interSlotUs`;
- long inter-packet gaps via `mbbUs`;
- different slot counts from 0 to 512.
