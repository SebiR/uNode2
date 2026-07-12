/*
 * uNodeArtNet - ArtPollDiscovery
 *
 * Connects an ESP8266 or ESP32 to Wi-Fi, calculates the active subnet's
 * directed broadcast address, and sends ArtPoll every five seconds. Incoming
 * ArtPollReply packets are decoded and printed with node name, IP addresses,
 * BindIndex, port direction, and complete 15-bit Port-Addresses.
 *
 * Data flow:
 *   this sketch --ArtPoll broadcast--> Art-Net nodes
 *   this sketch <--unicast ArtPollReply-- discovered nodes
 *
 * Before uploading:
 *   1. Set WIFI_SSID and WIFI_PASSWORD.
 *   2. Open Serial Monitor at 115200 baud.
 *   3. Ensure the Wi-Fi network permits broadcast traffic between stations.
 *
 * The example does not retain a node list. A production application would
 * typically identify entries by reported IP and BindIndex, update last-seen
 * timestamps, and expire nodes that stop replying.
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
static const uint32_t POLL_INTERVAL_MS = 5000;

WiFiUDP udp;
ArtNetNode artnet(udp);
IPAddress broadcastAddress;
uint32_t nextPollMs = 0;

static ArtNetNetworkConfig currentNetworkConfig() {
  ArtNetNetworkConfig network = {};
  network.ip = WiFi.localIP();
  network.subnet = WiFi.subnetMask();
  network.gateway = WiFi.gatewayIP();
  WiFi.macAddress(network.mac);
  network.dhcp = true;
  return network;
}

static IPAddress calculateBroadcast(
  const IPAddress& ip,
  const IPAddress& subnet) {
  // A directed broadcast keeps discovery inside the active IPv4 subnet:
  // broadcast = local address OR bitwise inverse of subnet mask.
  return IPAddress(
    ip[0] | (uint8_t)~subnet[0],
    ip[1] | (uint8_t)~subnet[1],
    ip[2] | (uint8_t)~subnet[2],
    ip[3] | (uint8_t)~subnet[3]);
}

static void printPort(
  const ArtPollReplyInfo& info,
  uint8_t port) {
  // PortTypes bit 6 advertises an input and bit 7 advertises an output.
  const bool input = (info.portTypes[port] & 0x40) != 0;
  const bool output = (info.portTypes[port] & 0x80) != 0;

  Serial.print("  port ");
  Serial.print(port + 1);
  Serial.print(": ");
  Serial.print(input ? "DMX input" : "");
  Serial.print(input && output ? " + " : "");
  Serial.print(output ? "DMX output" : "");

  if (input) {
    // Art-Net's 15-bit Port-Address is Net:7 | Sub-Net:4 | Universe:4.
    const uint16_t address =
      ((uint16_t)info.netSwitch << 8)
      | ((uint16_t)info.subSwitch << 4)
      | (info.swIn[port] & 0x0f);
    Serial.print(" SwIn=");
    Serial.print(address);
  }

  if (output) {
    const uint16_t address =
      ((uint16_t)info.netSwitch << 8)
      | ((uint16_t)info.subSwitch << 4)
      | (info.swOut[port] & 0x0f);
    Serial.print(" SwOut=");
    Serial.print(address);
  }

  Serial.println();
}

static void onArtPollReply(
  const ArtPollReplyInfo& info) {
  // senderIP is the actual UDP source. reportedIP is the address carried in
  // the ArtPollReply and may differ on unusual multi-interface devices.
  Serial.println();
  Serial.print(info.portName);
  Serial.print(" | sender ");
  Serial.print(info.senderIP);
  Serial.print(" | reported ");
  Serial.print(info.reportedIP);
  Serial.print(" | bind ");
  Serial.println(info.bindIndex);

  for (uint8_t port = 0; port < min<uint8_t>(info.numPorts, 4); port++) {
    printPort(info, port);
  }
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }

  const ArtNetNetworkConfig network = currentNetworkConfig();
  broadcastAddress = calculateBroadcast(network.ip, network.subnet);

  // Register the callback before begin(). ArtNetNode retains the function
  // pointer and invokes it whenever read() parses a valid ArtPollReply.
  artnet.setShortName("Discovery Tool");
  artnet.setLongName("uNodeArtNet ArtPoll Discovery Example");
  artnet.setArtPollReplyCallback(onArtPollReply);

  if (artnet.begin(network) != 0) {
    Serial.println("Unable to bind Art-Net UDP port");
  }

  Serial.print("ArtPoll broadcast: ");
  Serial.println(broadcastAddress);
}

void loop() {
  // ArtPollReply is received asynchronously, so continue processing UDP even
  // while no new ArtPoll needs to be transmitted.
  artnet.read();

  const uint32_t now = millis();
  if ((int32_t)(now - nextPollMs) >= 0) {
    nextPollMs = now + POLL_INTERVAL_MS;
    // ArtPollReply responses can be delayed by up to roughly one second by the
    // node, which is why read() must continue running after this call returns.
    artnet.sendArtPoll(broadcastAddress);
    Serial.println("ArtPoll sent");
  }
}
