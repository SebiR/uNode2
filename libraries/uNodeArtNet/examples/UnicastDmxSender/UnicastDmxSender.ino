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
static const IPAddress TARGET_IP(2, 0, 0, 1);
static const uint16_t PORT_ADDRESS = 0;
static const uint16_t SLOT_COUNT = 16;
static const uint32_t FRAME_INTERVAL_MS = 25;

WiFiUDP udp;
ArtNetNode artnet(udp);
uint32_t nextFrameMs = 0;
uint8_t chasePosition = 0;

static ArtNetNetworkConfig currentNetworkConfig() {
  ArtNetNetworkConfig network = {};
  network.ip = WiFi.localIP();
  network.subnet = WiFi.subnetMask();
  network.gateway = WiFi.gatewayIP();
  WiFi.macAddress(network.mac);
  network.dhcp = true;
  return network;
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }

  artnet.setShortName("WiFi Sender");
  artnet.setLongName("uNodeArtNet Unicast DMX Sender Example");
  artnet.setDirection(false);  // This node behaves like a physical DMX input.
  artnet.setStartingUniverse(PORT_ADDRESS);
  artnet.setUniverse(PORT_ADDRESS);
  artnet.setPhysical(0);
  artnet.setLength(SLOT_COUNT);

  if (artnet.begin(currentNetworkConfig()) != 0) {
    Serial.println("Unable to bind Art-Net UDP port");
  }
}

void loop() {
  artnet.read();  // Keep discovery and management replies responsive.

  const uint32_t now = millis();
  if ((int32_t)(now - nextFrameMs) < 0) {
    return;
  }

  nextFrameMs = now + FRAME_INTERVAL_MS;

  for (uint16_t slot = 0; slot < SLOT_COUNT; slot++) {
    artnet.setByte(slot, slot == chasePosition ? 255 : 0);
  }

  artnet.setPortInputActive(true);
  artnet.write(TARGET_IP);
  chasePosition = (chasePosition + 1) % SLOT_COUNT;
}
