# LXESP8266DMX uNode Fork

DMX/RDM driver for ESP8266 using the Arduino IDE.

This repository contains the uNode-maintained fork of Claude Heintz's
`LXESP8266DMX` library. It is based on upstream commit
`760972edc8e9239692a7a47f3db275ac64f7d5b8` from 2022-04-11.

Applications in this repository include the fork through its unique entry
point:

```cpp
#include <uNodeESP8266DMX.h>
```

The unique header prevents Arduino's library resolver from silently selecting
a globally installed upstream `LXESP8266DMX` copy. The original
`LXESP8266UARTDMX.h` remains available internally for source compatibility.

## uNode fork changes

- Uses UART0 for both directions:
  - DMX output: UART0 TX on GPIO1
  - DMX input: UART0 RX on GPIO3
- Adds UART receive-idle timeout handling so valid short DMX frames can finish
  without waiting for a full 512-slot frame or the next Break.
- Accepts received DMX frames containing one or more data slots while keeping
  the transmitter minimum at 24 slots.
- Drains the UART RX FIFO defensively and bounds received frame writes.
- Adds atomic `setFrame()` and `copyFrame()` APIs for transferring complete
  channel buffers between application and ISR-owned storage.
- Initializes internal state and buffers explicitly and validates direction
  pins, slots, capacities, and pointers.
- Fixes overlapping Table-of-Devices removal with `memmove()` and tightens TOD
  bounds checks.

## Hardware and API notes

Hardware Serial cannot be used while DMX is active. An external RS-485 line
driver is required.

For complete frame updates, prefer `setFrame()` and `copyFrame()` over loops
of individual `setSlot()`/`getSlot()` calls. Receive callbacks run inside the
UART interrupt and must only set an `IRAM_ATTR` flag that is processed later
from `loop()`.

The original source and this fork are distributed under the BSD 3-Clause
license in `LICENSE`. Original copyright and attribution are retained in the
source files.
