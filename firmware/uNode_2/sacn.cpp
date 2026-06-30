#include "sacn.h"

#include "artnet.h"
#include "config.h"
#include "dmx_frame.h"
#include "leds.h"

#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

#undef LOG_MODULE
#define LOG_MODULE "SACN"

static const uint16_t SACN_PORT = 5568;
static const uint16_t SACN_MIN_PACKET_SIZE = 126;
static const uint16_t SACN_MAX_PACKET_SIZE = 638;
static const uint32_t SACN_OUTPUT_TIMEOUT_MS = 2500;
static const uint32_t SACN_BIND_RETRY_MS = 5000;
static const uint32_t SACN_SOURCE_TIMEOUT_MS = 10000;
static const uint8_t MAX_SACN_SOURCES = 4;

static WiFiUDP sacnUdp;
static bool sacnSocketReady = false;
static bool sacnActive = false;
static bool sacnFailsafeActive = false;
static uint32_t nextSacnBindRetryMillis = 0;
static uint32_t lastSacnPacketMillis = 0;
static uint32_t sacnUdpPacketCounter = 0;
static uint32_t sacnPacketCounter = 0;
static uint32_t sacnFpsCounter = 0;
static uint32_t sacnCurrentFps = 0;
static uint32_t sacnFpsTimer = 0;
static uint32_t wrongUniverseCounter = 0;
static uint16_t lastWrongUniverse = 0;
static uint32_t malformedPacketCounter = 0;
static uint32_t sequenceDropCounter = 0;
static uint32_t protocolDropCounter = 0;
static uint32_t directionDropCounter = 0;
static uint32_t priorityDropCounter = 0;
static uint32_t streamTerminatedCounter = 0;
static uint8_t outgoingSequence = 1;
static uint8_t packetBuffer[SACN_MAX_PACKET_SIZE];

struct SacnSourceState {
  uint8_t cid[16];
  uint8_t sequence;
  uint8_t priority;
  uint32_t lastMillis;
  bool active;
};

static SacnSourceState sources[MAX_SACN_SOURCES];

/** @return Active interface address used for multicast membership. */
static IPAddress getLocalInterfaceIP() {
  if (WiFi.status() == WL_CONNECTED) {
    return WiFi.localIP();
  }

  return WiFi.softAPIP();
}

/** @return Multicast group for one sACN Universe. */
static IPAddress getUniverseMulticastAddress(uint16_t universe) {
  return IPAddress(
    239,
    255,
    (uint8_t)(universe >> 8),
    (uint8_t)(universe & 0xff));
}

/** @brief Writes a big-endian 16-bit value. */
static void put16(uint16_t offset, uint16_t value) {
  packetBuffer[offset] = value >> 8;
  packetBuffer[offset + 1] = value & 0xff;
}

/** @brief Writes a big-endian 32-bit value. */
static void put32(uint16_t offset, uint32_t value) {
  packetBuffer[offset] = (value >> 24) & 0xff;
  packetBuffer[offset + 1] = (value >> 16) & 0xff;
  packetBuffer[offset + 2] = (value >> 8) & 0xff;
  packetBuffer[offset + 3] = value & 0xff;
}

/** @return Big-endian 16-bit value from a received packet. */
static uint16_t read16(const uint8_t* packet, uint16_t offset) {
  return ((uint16_t)packet[offset] << 8)
         | packet[offset + 1];
}

/** @return Big-endian 32-bit value from a received packet. */
static uint32_t read32(const uint8_t* packet, uint16_t offset) {
  return ((uint32_t)packet[offset] << 24)
         | ((uint32_t)packet[offset + 1] << 16)
         | ((uint32_t)packet[offset + 2] << 8)
         | packet[offset + 3];
}

/** @return Lower 12-bit PDU length from one flags/length field. */
static uint16_t pduLength(const uint8_t* packet, uint16_t offset) {
  return read16(packet, offset) & 0x0fff;
}

uint16_t getSacnUniverse() {
  const uint16_t configured =
    getConfiguredUniverse();

  return configured == 0
    ? 1
    : configured;
}

/** @brief Builds a stable pseudo-CID from the ESP chip ID. */
static void fillCid(uint8_t* cid) {
  memset(cid, 0, 16);
  cid[0] = 0x75; // 'u'
  cid[1] = 0x4e; // 'N'
  cid[2] = 0x6f; // 'o'
  cid[3] = 0x64; // 'd'
  cid[4] = 0x65; // 'e'

  const uint32_t chipId =
    ESP.getChipId();

  cid[12] = (chipId >> 24) & 0xff;
  cid[13] = (chipId >> 16) & 0xff;
  cid[14] = (chipId >> 8) & 0xff;
  cid[15] = chipId & 0xff;
}

/** @return True when two 16-byte CIDs match. */
static bool cidEquals(
  const uint8_t* left,
  const uint8_t* right) {
  return memcmp(left, right, 16) == 0;
}

/** @brief Clears tracked source sequencing and priority state. */
static void clearSources() {
  for (uint8_t i = 0; i < MAX_SACN_SOURCES; i++) {
    sources[i].active = false;
  }
}

/** @brief Expires inactive sACN sources. */
static void expireSources(uint32_t now) {
  for (uint8_t i = 0; i < MAX_SACN_SOURCES; i++) {
    if (sources[i].active
        && now - sources[i].lastMillis >= SACN_SOURCE_TIMEOUT_MS) {
      sources[i].active = false;
    }
  }
}

/** @return Highest priority among active sACN sources. */
static uint8_t getHighestActivePriority() {
  uint8_t highest = 0;

  for (uint8_t i = 0; i < MAX_SACN_SOURCES; i++) {
    if (sources[i].active
        && sources[i].priority > highest) {
      highest = sources[i].priority;
    }
  }

  return highest;
}

/** @return Existing, free, or oldest source state slot. */
static uint8_t getSourceIndex(
  const uint8_t* cid,
  uint32_t now) {
  uint8_t oldestIndex = 0;
  uint32_t oldestAge = 0;

  for (uint8_t i = 0; i < MAX_SACN_SOURCES; i++) {
    if (sources[i].active
        && cidEquals(sources[i].cid, cid)) {
      return i;
    }

    if (!sources[i].active) {
      return i;
    }

    const uint32_t age =
      now - sources[i].lastMillis;

    if (age >= oldestAge) {
      oldestAge = age;
      oldestIndex = i;
    }
  }

  return oldestIndex;
}

/** @return True when one sequence number follows another, with wraparound. */
static bool isSequenceNewer(
  uint8_t previous,
  uint8_t current) {
  if (current == previous) {
    return false;
  }

  return (uint8_t)(current - previous) < 128;
}

/** @brief Applies the configured output failsafe for sACN live data. */
static void applySacnFailsafe() {
  if (config.liveProtocol != LIVE_PROTOCOL_SACN) {
    protocolDropCounter++;
    return;
  }

  if (config.direction != ARTNET_TO_DMX) {
    directionDropCounter++;
    return;
  }

  sacnFailsafeActive = true;

  uint8_t frame[DMX_CHANNEL_COUNT];
  bool shouldSetFrame = true;

  switch (config.failsafeMode) {
    case FAILSAFE_ZERO:
      memset(frame, 0, sizeof(frame));
      break;

    case FAILSAFE_FULL:
      memset(frame, 255, sizeof(frame));
      break;

    case FAILSAFE_SCENE:
      if (!loadFailsafeScene(frame)) {
        memset(frame, 0, sizeof(frame));
      }
      break;

    case FAILSAFE_HOLD:
    default:
      shouldSetFrame = false;
      break;
  }

  if (shouldSetFrame) {
    setDmxFrame(frame, DMX_CHANNEL_COUNT, true);
  }
}

/** @brief Opens the sACN socket and joins the configured multicast group. */
static bool bindSacnSocket() {
  sacnUdp.stop();

  const uint16_t universe =
    getSacnUniverse();

  const IPAddress localIP =
    getLocalInterfaceIP();
  const IPAddress multicastIP =
    getUniverseMulticastAddress(universe);

  bool ok = false;

  if (localIP != IPAddress()) {
    ok = sacnUdp.beginMulticast(
      localIP,
      multicastIP,
      SACN_PORT);
  }

  if (!ok) {
    ok = sacnUdp.begin(SACN_PORT);
  }

  if (ok) {
    LOG_INFO_PRINT("sACN listening on Universe ");
    LOG_PRINT(LOG_LEVEL_INFO, universe);
    LOG_PRINT(LOG_LEVEL_INFO, " multicast ");
    LOG_PRINTLN(LOG_LEVEL_INFO, multicastIP);
  } else {
    LOG_WARN("sACN UDP bind failed");
  }

  return ok;
}

bool initSacn() {
  LOG_SECTION("sACN Init");

  sacnSocketReady =
    bindSacnSocket();

  if (!sacnSocketReady) {
    nextSacnBindRetryMillis =
      millis() + SACN_BIND_RETRY_MS;
  }

  sacnFpsTimer =
    millis();

  return sacnSocketReady;
}

void handleSacnNetworkChange() {
  LOG_INFO("sACN network interface changed");

  clearSources();
  sacnActive = false;
  sacnFailsafeActive = false;
  lastSacnPacketMillis = 0;

  sacnSocketReady =
    bindSacnSocket();

  if (!sacnSocketReady) {
    nextSacnBindRetryMillis =
      millis() + SACN_BIND_RETRY_MS;
  }
}

/** @return True when the packet has the fixed E1.31 identifiers and vectors. */
static bool hasValidSacnStructure(
  const uint8_t* packet,
  uint16_t length) {
  static const uint8_t ACN_PID[12] = {
    'A', 'S', 'C', '-', 'E', '1', '.', '1', '7', 0x00, 0x00, 0x00
  };

  if (length < SACN_MIN_PACKET_SIZE
      || read16(packet, 0) != 0x0010
      || read16(packet, 2) != 0x0000
      || memcmp(packet + 4, ACN_PID, sizeof(ACN_PID)) != 0
      || read32(packet, 18) != 0x00000004
      || read32(packet, 40) != 0x00000002
      || packet[117] != 0x02
      || packet[118] != 0xa1
      || read16(packet, 119) != 0x0000
      || read16(packet, 121) != 0x0001
      || packet[125] != 0x00) {
    return false;
  }

  if (pduLength(packet, 16) < 110
      || pduLength(packet, 38) < 88
      || pduLength(packet, 115) < 11) {
    return false;
  }

  const uint16_t propertyCount =
    read16(packet, 123);

  return propertyCount >= 1
         && 125 + propertyCount <= length;
}

/** @brief Handles one valid sACN data packet. */
static void handleSacnPacket(
  const uint8_t* packet,
  uint16_t length) {
  if (!hasValidSacnStructure(packet, length)) {
    malformedPacketCounter++;
    return;
  }

  const uint16_t universe =
    read16(packet, 113);

  if (universe != getSacnUniverse()) {
    wrongUniverseCounter++;
    lastWrongUniverse = universe;
    return;
  }

  if (config.liveProtocol != LIVE_PROTOCOL_SACN) {
    protocolDropCounter++;
    return;
  }

  if (config.direction != ARTNET_TO_DMX) {
    directionDropCounter++;
    return;
  }

  const uint8_t priority =
    packet[108];
  const uint8_t sequence =
    packet[111];
  const uint8_t options =
    packet[112];
  const bool streamTerminated =
    (options & 0x40) != 0;
  const uint16_t propertyCount =
    read16(packet, 123);
  const uint16_t slots =
    constrain(
      (uint16_t)(propertyCount - 1),
      (uint16_t)0,
      (uint16_t)DMX_CHANNEL_COUNT);
  const uint8_t* cid =
    packet + 22;
  const uint32_t now =
    millis();

  expireSources(now);

  const uint8_t sourceIndex =
    getSourceIndex(cid, now);
  SacnSourceState& source =
    sources[sourceIndex];

  const bool existingSource =
    source.active
    && cidEquals(source.cid, cid);

  if (existingSource
      && !isSequenceNewer(source.sequence, sequence)) {
    sequenceDropCounter++;
    return;
  }

  const uint8_t highestPriority =
    getHighestActivePriority();

  if (priority < highestPriority
      && (!existingSource
          || source.priority < highestPriority)) {
    priorityDropCounter++;
    return;
  }

  memcpy(source.cid, cid, 16);
  source.sequence = sequence;
  source.priority = priority;
  source.lastMillis = now;
  source.active = !streamTerminated;

  if (streamTerminated) {
    streamTerminatedCounter++;
    return;
  }

  setDmxFrame(packet + 126, slots, true);

  sacnPacketCounter++;
  sacnFpsCounter++;
  lastSacnPacketMillis = now;
  sacnActive = true;
  sacnFailsafeActive = false;

  flashDMXOutputLED();
}

void updateSacn() {
  uint32_t now = millis();

  if (!sacnSocketReady) {
    if ((int32_t)(now - nextSacnBindRetryMillis) >= 0) {
      sacnSocketReady =
        bindSacnSocket();
      nextSacnBindRetryMillis =
        now + SACN_BIND_RETRY_MS;
    }

    return;
  }

  int packetSize =
    sacnUdp.parsePacket();

  while (packetSize > 0) {
    if (packetSize > SACN_MAX_PACKET_SIZE) {
      malformedPacketCounter++;
      while (sacnUdp.available()) {
        sacnUdp.read();
      }
    } else {
      const int bytesRead =
        sacnUdp.read(
          packetBuffer,
          sizeof(packetBuffer));

      if (bytesRead > 0) {
        sacnUdpPacketCounter++;
        handleSacnPacket(
          packetBuffer,
          (uint16_t)bytesRead);
      }
    }

    packetSize =
      sacnUdp.parsePacket();
  }

  now = millis();
  expireSources(now);

  if (sacnActive
      && now - lastSacnPacketMillis > SACN_OUTPUT_TIMEOUT_MS) {
    sacnActive = false;
    applySacnFailsafe();
  }

  if (now - sacnFpsTimer >= 1000) {
    sacnCurrentFps = sacnFpsCounter;
    sacnFpsCounter = 0;
    sacnFpsTimer = now;
  }
}

/** @brief Builds one sACN data packet from the shared DMX frame. */
static uint16_t buildSacnDataPacket() {
  const uint16_t slots =
    constrain(
      getDmxFrameLength(),
      (uint16_t)1,
      (uint16_t)DMX_CHANNEL_COUNT);
  const uint16_t propertyCount =
    slots + 1;
  const uint16_t packetLength =
    126 + slots;

  memset(packetBuffer, 0, packetLength);

  put16(0, 0x0010);
  put16(2, 0x0000);

  static const uint8_t ACN_PID[12] = {
    'A', 'S', 'C', '-', 'E', '1', '.', '1', '7', 0x00, 0x00, 0x00
  };
  memcpy(packetBuffer + 4, ACN_PID, sizeof(ACN_PID));

  put16(16, 0x7000 | (packetLength - 16));
  put32(18, 0x00000004);
  fillCid(packetBuffer + 22);

  put16(38, 0x7000 | (packetLength - 38));
  put32(40, 0x00000002);

  const char* name =
    config.sacnSourceName.length() > 0
      ? config.sacnSourceName.c_str()
      : config.longName.c_str();
  strncpy(
    (char*)packetBuffer + 44,
    name,
    63);

  packetBuffer[108] = config.sacnPriority;
  put16(109, 0x0000);
  packetBuffer[111] = outgoingSequence++;

  if (outgoingSequence == 0) {
    outgoingSequence = 1;
  }

  packetBuffer[112] = 0x00;
  put16(113, getSacnUniverse());

  put16(115, 0x7000 | (packetLength - 115));
  packetBuffer[117] = 0x02;
  packetBuffer[118] = 0xa1;
  put16(119, 0x0000);
  put16(121, 0x0001);
  put16(123, propertyCount);
  packetBuffer[125] = 0x00;

  for (uint16_t i = 0; i < slots; i++) {
    packetBuffer[126 + i] =
      getDmxChannel(i);
  }

  return packetLength;
}

bool sendSacnFrame() {
  if (!sacnSocketReady) {
    return false;
  }

  const uint16_t universe =
    getSacnUniverse();
  const IPAddress target =
    getUniverseMulticastAddress(universe);
  const uint16_t packetLength =
    buildSacnDataPacket();

  if (!sacnUdp.beginPacketMulticast(
        target,
        SACN_PORT,
        getLocalInterfaceIP())) {
    return false;
  }

  const size_t written =
    sacnUdp.write(
      packetBuffer,
      packetLength);

  if (!sacnUdp.endPacket()
      || written != packetLength) {
    return false;
  }

  flashArtNetLED();
  return true;
}

bool isSacnSocketReady() {
  return sacnSocketReady;
}

bool isSacnActive() {
  return sacnActive;
}

bool isSacnFailsafeActive() {
  return sacnFailsafeActive;
}

uint32_t getSacnPacketCount() {
  return sacnPacketCounter;
}

uint32_t getSacnUdpPacketCount() {
  return sacnUdpPacketCounter;
}

uint32_t getSacnFPS() {
  return sacnCurrentFps;
}

uint32_t getLastSacnPacketAge() {
  if (!lastSacnPacketMillis) {
    return 0;
  }

  return millis() - lastSacnPacketMillis;
}

uint32_t getSacnWrongUniverseCount() {
  return wrongUniverseCounter;
}

uint16_t getSacnLastWrongUniverse() {
  return lastWrongUniverse;
}

uint32_t getSacnMalformedPacketCount() {
  return malformedPacketCounter;
}

uint32_t getSacnSequenceDropCount() {
  return sequenceDropCounter;
}

uint32_t getSacnProtocolDropCount() {
  return protocolDropCounter;
}

uint32_t getSacnDirectionDropCount() {
  return directionDropCounter;
}

uint32_t getSacnPriorityDropCount() {
  return priorityDropCounter;
}

uint32_t getSacnStreamTerminatedCount() {
  return streamTerminatedCounter;
}
