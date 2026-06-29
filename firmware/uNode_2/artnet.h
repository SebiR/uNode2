#pragma once

#include <Arduino.h>

#include "ArtnetnodeWifi.h"
#include "config.h"

extern ArtnetnodeWifi artnet;

struct ArtNetSubscriberInfo {
  IPAddress ip;
  char name[19];
  uint8_t bindIndex;
  uint8_t inputPortMask;
  uint8_t outputPortMask;
  uint32_t lastSeenMillis;
};

struct ArtNetSourceInfo {
  IPAddress ip;
  uint8_t physical;
  uint32_t lastSeenMillis;
  bool active;
  bool winning;
};

/** @brief Initializes the Art-Net UDP socket, node identity, and callbacks. */
bool initArtNet();
/** @brief Processes incoming packets, polling, and subscriber expiry. */
void updateArtNet();
/** @brief Rebinds Art-Net after the active network interface changes. */
void handleArtNetNetworkChange();

/** @return Directed broadcast address of the active network interface. */
IPAddress getArtNetBroadcast();

/** @brief Sends an immediate ArtPoll and opens the discovery window. */
void startArtNetDiscovery();
/** @return True while an explicitly requested discovery window is active. */
bool isArtNetDiscoveryActive();
/** @return Number of subscribers matching the configured Port-Address. */
uint8_t getArtNetSubscriberCount();
/**
 * @brief Copies one subscriber record.
 * @param index Zero-based subscriber index.
 * @param subscriber Destination receiving the copied record.
 * @return True when the index exists.
 */
bool getArtNetSubscriber(
  uint8_t index,
  ArtNetSubscriberInfo& subscriber);
/** @return Monotonically changing version of the subscriber set. */
uint32_t getArtNetSubscriberVersion();
/** @return millis() timestamp of the last transmitted ArtPoll. */
uint32_t getLastSubscriberPollMillis();

/** @return Configured 15-bit Art-Net Port-Address. */
uint16_t getConfiguredUniverse();

/** @return Number of accepted ArtDmx packets. */
uint32_t getArtDmxCounter();
/** @return Accepted ArtDmx frames during the previous second. */
uint32_t getArtNetFPS();
/** @return Milliseconds since the last accepted ArtDmx packet, or zero. */
uint32_t getLastArtNetPacketAge();
/** @return Number of accepted ArtSync packets. */
uint32_t getArtSyncCounter();
/** @return Milliseconds since the last accepted ArtSync packet, or zero. */
uint32_t getLastArtSyncAge();
/** @return True while ArtSync buffering is active. */
bool isArtSyncActive();
/** @return True when ArtDmx data is buffered and waiting for ArtSync. */
bool isArtSyncPendingOutput();
/** @return Low-level oversized Art-Net packet counter. */
uint32_t getArtNetOversizedPacketCount();
/** @return Low-level short UDP packet counter. */
uint32_t getArtNetShortPacketCount();
/** @return Low-level invalid Art-Net ID packet counter. */
uint32_t getArtNetInvalidIdPacketCount();
/** @return Low-level unsupported protocol-version counter. */
uint32_t getArtNetUnsupportedProtocolCount();
/** @return Low-level malformed Art-Net packet counter. */
uint32_t getArtNetMalformedPacketCount();
/** @return Low-level unsupported opcode counter. */
uint32_t getArtNetUnsupportedOpcodeCount();
/** @return ArtDmx packets ignored because they target another Port-Address. */
uint32_t getArtNetWrongUniverseCount();
/** @return Last wrong ArtDmx Port-Address seen by the node. */
uint16_t getArtNetLastWrongUniverse();
/** @return Milliseconds since the last wrong ArtDmx Port-Address, or zero. */
uint32_t getArtNetLastWrongUniverseAge();
/** @return True when the wrong Port-Address warning is currently relevant. */
bool isArtNetWrongUniverseWarningActive();
/** @return ArtDmx packets ignored because the node is not in output mode. */
uint32_t getArtNetDirectionDropCount();
/** @return ArtDmx packets dropped by sequence tracking. */
uint32_t getArtNetSequenceDropCount();
/** @return ArtDmx packets dropped by AcCancelMerge source lock. */
uint32_t getArtNetMergeLockDropCount();
/** @return ArtDmx packets dropped because a third merge source appeared. */
uint32_t getArtNetMergeThirdSourceDropCount();
/** @return Number of ArtSync timeouts returning to asynchronous output. */
uint32_t getArtNetSyncTimeoutCount();
/** @return Number of currently active ArtDmx merge/input sources. */
uint8_t getArtNetSourceCount();
/** @brief Copies one active ArtDmx source record. */
bool getArtNetSource(
  uint8_t index,
  ArtNetSourceInfo& source);
/** @return Number of ArtPollReply attempts made by this node. */
uint32_t getArtPollCount();
/** @return millis() timestamp of the last ArtPollReply attempt. */
uint32_t getLastArtPollMillis();

/** @return True while ArtDmx reception is considered active. */
bool isArtNetActive();
/** @return True after the configured ArtDmx timeout has applied failsafe. */
bool isOutputFailsafeActive();
/** @return Human-readable name of the configured failsafe mode. */
const char* getFailsafeModeName();
/** @brief Stores the current output frame as the persistent failsafe scene. */
bool recordFailsafeScene(String& error);

/** @brief Toggles the node between Locate and Normal indicator modes. */
void toggleArtNetLocate();
/** @return True when the node reports the Art-Net squawking state. */
bool isSquawking();

/** @brief Applies the configured physical RS-485 direction. */
void updateDirection();

/**
 * @brief Applies live Art-Net/DMX runtime changes after a persisted web save.
 * @param previous Configuration active before the save.
 * @param error Human-readable error if a runtime action failed.
 * @return True when all runtime changes were applied without a full reboot.
 */
bool applyArtNetRuntimeConfig(
  const Config& previous,
  String& error);

/** @return True when the current frame reaches at least one subscriber. */
bool sendArtNetFrame();

