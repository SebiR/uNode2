#include <Arduino.h>
#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <uNodeArtNet.h>

static byte macAddress[] = { 0x02, 0x55, 0x4E, 0x4F, 0x44, 0x45 };
static const IPAddress FALLBACK_IP(2, 0, 0, 10);
static const uint16_t PORT_ADDRESS = 0;

EthernetUDP udp;
ArtNetNode artnet(udp);
bool usingDhcp = false;

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

  usingDhcp = Ethernet.begin(macAddress) != 0;
  if (!usingDhcp) {
    Ethernet.begin(macAddress, FALLBACK_IP);
  }

  delay(1000);
  Serial.print("Ethernet address: ");
  Serial.println(Ethernet.localIP());

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
  Ethernet.maintain();
  artnet.read();
}
