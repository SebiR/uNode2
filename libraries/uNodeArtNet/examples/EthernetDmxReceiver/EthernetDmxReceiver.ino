/*
 * uNodeArtNet - EthernetDmxReceiver
 *
 * Demonstrates that ArtNetNode is independent of Wi-Fi. The sketch requests
 * an address through DHCP using EthernetUDP and falls back to 2.0.0.10 if no
 * DHCP server responds. Incoming ArtDmx packets are printed to Serial.
 *
 * Data flow:
 *   Art-Net controller -> Ethernet -> EthernetUDP -> ArtNetNode -> onArtDmx()
 *
 * Before uploading:
 *   1. Select an Arduino-compatible Ethernet library for the installed chip
 *      (for example Ethernet for W5100/W5500 or UIPEthernet for ENC28J60).
 *   2. Adjust the Ethernet chip-select pin in that library or board setup.
 *   3. Give every device a unique MAC address and change FALLBACK_IP if needed.
 *   4. Send ArtDmx to Port-Address 0; some controller UIs display it as U1.
 *
 * No physical DMX driver is included. The callback is the integration point
 * for a UART/PIO DMX transmitter or any other consumer of the slot values.
 */

#include <Arduino.h>
#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <uNodeArtNet.h>

static byte macAddress[] = { 0x02, 0x55, 0x4E, 0x4F, 0x44, 0x45 };
static const IPAddress FALLBACK_IP(2, 0, 0, 10);
static const uint16_t PORT_ADDRESS = 0;

// EthernetUDP implements Arduino's common UDP base class, so no Art-Net code
// changes are required compared with the Wi-Fi receiver example.
EthernetUDP udp;
ArtNetNode artnet(udp);
bool usingDhcp = false;

/** @return Active Ethernet identity advertised by the Art-Net node. */
static ArtNetNetworkConfig currentNetworkConfig() {
  ArtNetNetworkConfig network = {};
  network.ip = Ethernet.localIP();
  network.subnet = Ethernet.subnetMask();
  network.gateway = Ethernet.gatewayIP();
  memcpy(network.mac, macAddress, sizeof(network.mac));
  network.dhcp = usingDhcp;
  return network;
}

static void onArtDmx(
  uint16_t portAddress,
  uint16_t length,
  uint8_t sequence,
  uint8_t* data) {
  // Consume or copy data before the next artnet.read(), because it points into
  // the reusable receive buffer owned by ArtNetNode.
  Serial.print("ArtDmx port-address=");
  Serial.print(portAddress);
  Serial.print(" sequence=");
  Serial.print(sequence);
  Serial.print(" slots=");
  Serial.print(length);
  Serial.print(" first=");
  Serial.println(length > 0 ? data[0] : 0);
  artnet.setPortOutputActive(true);
}

void setup() {
  Serial.begin(115200);

  // Try DHCP first so the same sketch works on a normal LAN. The static
  // fallback remains convenient for a direct controller-to-node test network.
  usingDhcp = Ethernet.begin(macAddress) != 0;
  if (!usingDhcp) {
    Ethernet.begin(macAddress, FALLBACK_IP);
  }

  delay(1000);
  Serial.print("Ethernet address: ");
  Serial.println(Ethernet.localIP());

  // Configure how this single conceptual output port appears in ArtPollReply.
  artnet.setShortName("Ethernet Receiver");
  artnet.setLongName("uNodeArtNet Ethernet DMX Receiver Example");
  artnet.setDirection(true);  // Art-Net input drives a physical DMX output.
  artnet.setStartingUniverse(PORT_ADDRESS);
  artnet.setArtDmxCallback(onArtDmx);

  if (artnet.begin(currentNetworkConfig()) != 0) {
    Serial.println("Unable to bind Art-Net UDP port");
  }
}

void loop() {
  // Maintain a DHCP lease when DHCP was used. Calling this with a static
  // address is harmless in the common Ethernet implementations.
  Ethernet.maintain();

  // Art-Net parsing and delayed management replies are cooperative, so read()
  // should run as frequently as possible.
  artnet.read();
}
