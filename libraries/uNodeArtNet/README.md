# uNodeArtNet

`uNodeArtNet` is the reusable Art-Net protocol core developed as part of the
uNode 2 firmware. It accepts any Arduino networking implementation that
provides the standard `UDP` interface, including Wi-Fi and Ethernet transports.

The application owns the UDP object and supplies the active interface identity:

```cpp
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <uNodeArtNet.h>

EthernetUDP udp;
ArtNetNode artnet(udp);

ArtNetNetworkConfig network = {};
network.ip = Ethernet.localIP();
network.subnet = Ethernet.subnetMask();
network.gateway = Ethernet.gatewayIP();
memcpy(network.mac, macAddress, sizeof(network.mac));
network.dhcp = true;

artnet.begin(network);
```

DMX drivers, merging, failsafe behavior, LEDs, persistent configuration and web
interfaces intentionally remain application responsibilities.

## License

This code is derived from GPLv2-licensed `ArtnetnodeWifi` work by Charles
Yarnold and Stephan Ruloff and is distributed under GPL-2.0-only. See the
copyright headers in the source files.
