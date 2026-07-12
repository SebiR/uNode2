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

WiFiUDP udp;
ArtNetNode artnet(udp);

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

  artnet.setShortName("WiFi Receiver");
  artnet.setLongName("uNodeArtNet WiFi DMX Receiver Example");
  artnet.setDirection(true);  // Art-Net input drives a physical DMX output.
  artnet.setStartingUniverse(PORT_ADDRESS);
  artnet.setArtDmxCallback(onArtDmx);

  if (artnet.begin(currentNetworkConfig()) != 0) {
    Serial.println("Unable to bind Art-Net UDP port");
  }
}

void loop() {
  artnet.read();
}
