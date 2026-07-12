/*
 * uNodeArtNet - WiFiDmxReceiver
 *
 * Connects an ESP8266 or ESP32 to an existing Wi-Fi network and listens for
 * ArtDmx packets on the standard Art-Net UDP port 6454. Every accepted packet
 * invokes onArtDmx(), which prints its Port-Address, sequence number, length,
 * and first eight slot values to the USB serial terminal.
 *
 * Data flow:
 *   Art-Net controller -> Wi-Fi -> WiFiUDP -> ArtNetNode -> onArtDmx()
 *
 * Before uploading:
 *   1. Set WIFI_SSID and WIFI_PASSWORD below.
 *   2. Configure the controller to send to this board's IP address or the
 *      subnet broadcast address.
 *   3. Select Art-Net Port-Address 0. Some controller UIs display it as U1.
 *
 * This example only prints received values. Replace the callback body with a
 * DMX driver, PWM output, LED control, or another application as needed.
 */

#include <Arduino.h>

#if defined(ARDUINO_ARCH_ESP8266)
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#elif defined(ARDUINO_ARCH_ESP32)
#include <WiFi.h>
#include <WiFiUdp.h>
#else
#error "This example requires an ESP8266 or ESP32 Wi-Fi board"
#endif

#include <uNodeArtNet.h>

static const char* WIFI_SSID = "your-ssid";
static const char* WIFI_PASSWORD = "your-password";
static const uint16_t PORT_ADDRESS = 0;

// The application owns the UDP transport. ArtNetNode only stores a reference,
// which is what allows the same protocol implementation to use other UDP APIs.
WiFiUDP udp;
ArtNetNode artnet(udp);

/** @return Identity of the active interface for ArtPollReply and ArtIpProg. */
static ArtNetNetworkConfig currentNetworkConfig() {
  ArtNetNetworkConfig network = {};
  network.ip = WiFi.localIP();
  network.subnet = WiFi.subnetMask();
  network.gateway = WiFi.gatewayIP();
  WiFi.macAddress(network.mac);
  network.dhcp = true;
  return network;
}

static void onArtDmx(
  uint16_t portAddress,
  uint16_t length,
  uint8_t sequence,
  uint8_t* data) {
  // The data pointer addresses the library's receive buffer. Consume or copy
  // values inside the callback before the next call to artnet.read().
  Serial.print("ArtDmx port-address=");
  Serial.print(portAddress);
  Serial.print(" sequence=");
  Serial.print(sequence);
  Serial.print(" slots=");
  Serial.print(length);
  Serial.print(" values:");

  for (uint16_t index = 0; index < min<uint16_t>(length, 8); index++) {
    Serial.print(' ');
    Serial.print(data[index]);
  }

  Serial.println();
  // Advertise in subsequent ArtPollReply packets that this output port has
  // received live data. A real node can clear the flag after a timeout.
  artnet.setPortOutputActive(true);
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print('.');
  }

  Serial.println();
  Serial.print("Connected: ");
  Serial.println(WiFi.localIP());

  // Configure the node information advertised in ArtPollReply.
  artnet.setShortName("WiFi Receiver");
  artnet.setLongName("uNodeArtNet WiFi DMX Receiver Example");
  artnet.setDirection(true);  // Art-Net input drives a physical DMX output.
  artnet.setStartingUniverse(PORT_ADDRESS);
  artnet.setArtDmxCallback(onArtDmx);

  // begin() binds UDP port 6454. It does not connect the network interface;
  // network setup remains the responsibility of the application.
  if (artnet.begin(currentNetworkConfig()) != 0) {
    Serial.println("Unable to bind Art-Net UDP port");
  }
}

void loop() {
  // Call read() frequently. Besides ArtDmx, it handles ArtPoll, ArtAddress,
  // ArtSync, ArtIpProg, and delayed ArtPollReply transmissions.
  artnet.read();
}
