#include "artnet.h"

#include "config.h"
#include "dmx.h"
#include "dmx_frame.h"
#include "hardware.h"
#include "leds.h"

#include "ArtnetnodeWifi.h"

#include <LittleFS.h>

#undef LOG_MODULE
#define LOG_MODULE "ARTNET"

ArtnetnodeWifi artnet;

static uint32_t artDmxCounter = 0;

static uint32_t lastArtNetPacketMillis = 0;

static uint32_t fpsCounter = 0;
static uint32_t currentFPS = 0;
static uint32_t fpsTimer = 0;

static bool artnetActive = false;
static bool outputFailsafeActive = false;
static bool artnetSocketReady = false;
static uint32_t nextArtNetBindRetryMillis = 0;
static const uint32_t ARTNET_BIND_RETRY_MS = 5000;
static const uint32_t ARTNET_OUTPUT_TIMEOUT_MS = 5000;
static const uint32_t WRONG_UNIVERSE_WARNING_MS = 5000;
static const uint32_t ARTSYNC_TIMEOUT_MS = 4000;
static const uint32_t ART_IP_PROG_RESTART_DELAY_MS = 1500;
static const char* FAILSAFE_SCENE_PATH = "/failsafe.bin";

static const uint8_t MAX_ARTDMX_SEQUENCE_SOURCES = 4;
static const uint32_t ARTDMX_SEQUENCE_TIMEOUT_MS = 10000;
static const uint32_t ARTDMX_MERGE_SOURCE_TIMEOUT_MS = 10000;

static const uint8_t MAX_ARTNET_SUBSCRIBERS = 16;
static const uint32_t DISCOVERY_DURATION_MS = 3000;
static const uint32_t SUBSCRIBER_POLL_INTERVAL_MS = 2500;
static const uint32_t SUBSCRIBER_TIMEOUT_MS = 7500;

struct ArtDmxSequenceState {
  IPAddress senderIP;
  uint8_t physical;
  uint8_t sequence;
  uint32_t lastMillis;
  bool active;
};

struct ArtDmxMergeSource {
  IPAddress senderIP;
  uint8_t physical;
  uint8_t frame[DMX_CHANNEL_COUNT];
  uint32_t lastMillis;
  bool active;
};

static ArtDmxSequenceState artDmxSequences[MAX_ARTDMX_SEQUENCE_SOURCES];
static ArtDmxMergeSource mergeSources[2];
static uint8_t lastMergeSourceIndex = 0;
static bool cancelMergePending = false;
static bool mergeLockedToSingleSource = false;
static IPAddress mergeLockIP;
static uint8_t mergeLockPhysical = 0;
static bool artSyncActive = false;
static bool artSyncPendingOutput = false;
static uint32_t lastArtSyncMillis = 0;
static uint32_t artSyncCounter = 0;
static uint32_t wrongUniverseCounter = 0;
static uint16_t lastWrongUniverse = 0;
static uint32_t lastWrongUniverseMillis = 0;
static uint32_t directionDropCounter = 0;
static uint32_t sequenceDropCounter = 0;
static uint32_t mergeLockDropCounter = 0;
static uint32_t mergeThirdSourceDropCounter = 0;
static uint32_t artSyncTimeoutCounter = 0;

static ArtNetSubscriberInfo subscribers[MAX_ARTNET_SUBSCRIBERS];
static uint8_t subscriberCount = 0;
static uint32_t subscriberVersion = 1;
static uint32_t lastSubscriberPollMillis = 0;
static bool discoveryActive = false;
static uint32_t discoveryStartedMillis = 0;
static bool artIpProgRestartPending = false;
static uint32_t artIpProgRestartMillis = 0;
static bool failsafeSceneRecordPending = false;

/** @brief Removes all currently known subscribers. */
static void clearSubscribers();
/** @brief Clears remembered ArtDmx sequence state for all senders. */
static void clearArtDmxSequences();
/** @brief Clears ArtDmx output merge state. */
static void clearArtDmxMerge();
/** @brief Applies the configured merge mode to the shared DMX frame. */
static void applyMergedOutputFrame();
/** @brief Updates ArtPollReply merge-state and merge-mode bits. */
static void updateMergePollReplyStatus();
/** @brief Clears ArtSync buffering state. */
static void clearArtSyncState();

/** @return IPAddress parsed from a configuration string, or fallback. */
static IPAddress parseConfigAddress(
  const String& value,
  IPAddress fallback) {
  IPAddress address;

  if (address.fromString(value)) {
    return address;
  }

  return fallback;
}

uint16_t getConfiguredUniverse() {
  return (config.net * 256) + (config.subnetId * 16) + config.universe;
}

/** @return Printable label for one failsafe mode. */
static const char* getFailsafeModeName(
  FailsafeMode mode) {
  switch (mode) {
    case FAILSAFE_ZERO:
      return "All to Zero";

    case FAILSAFE_FULL:
      return "All to Full";

    case FAILSAFE_SCENE:
      return "Failsafe Scene";

    case FAILSAFE_HOLD:
    default:
      return "Hold";
  }
}

const char* getFailsafeModeName() {
  return getFailsafeModeName(
    config.failsafeMode);
}

/** @brief Updates ArtPollReply Status3 to match the configured failsafe mode. */
static void updateFailsafePollReplyStatus() {
  artnet.setFailsafeStatus(
    static_cast<uint8_t>(config.failsafeMode),
    true);
}

/** @brief Writes the current shared DMX frame to LittleFS. */
bool recordFailsafeScene(
  String& error) {
  uint8_t scene[DMX_CHANNEL_COUNT];

  copyDmxFrame(
    scene,
    DMX_CHANNEL_COUNT);

  yield();

  File file =
    LittleFS.open(
      FAILSAFE_SCENE_PATH,
      "w");

  if (!file) {
    error = "Failed to create failsafe scene";
    return false;
  }

  const size_t written =
    file.write(
      scene,
      sizeof(scene));

  yield();

  file.close();

  if (written != sizeof(scene)) {
    LittleFS.remove(
      FAILSAFE_SCENE_PATH);
    error = "Failed to write complete failsafe scene";
    return false;
  }

  error = "";
  return true;
}

/** @brief Loads the persisted failsafe scene into the supplied buffer. */
static bool loadFailsafeScene(
  uint8_t* scene) {
  if (!scene
      || !LittleFS.exists(FAILSAFE_SCENE_PATH)) {
    return false;
  }

  yield();

  File file =
    LittleFS.open(
      FAILSAFE_SCENE_PATH,
      "r");

  if (!file
      || file.size() != DMX_CHANNEL_COUNT) {
    if (file) {
      file.close();
    }

    return false;
  }

  const size_t bytesRead =
    file.read(
      scene,
      DMX_CHANNEL_COUNT);

  yield();

  file.close();
  return bytesRead == DMX_CHANNEL_COUNT;
}

/** @brief Applies the configured output failsafe to the shared DMX frame. */
static void applyOutputFailsafe() {
  if (config.direction != ARTNET_TO_DMX) {
    return;
  }

  outputFailsafeActive = true;
  clearArtDmxMerge();
  clearArtSyncState();

  uint8_t frame[DMX_CHANNEL_COUNT];
  bool shouldSetFrame = true;
  bool sceneMissing = false;

  switch (config.failsafeMode) {
    case FAILSAFE_ZERO:
      memset(
        frame,
        0,
        sizeof(frame));
      break;

    case FAILSAFE_FULL:
      memset(
        frame,
        255,
        sizeof(frame));
      break;

    case FAILSAFE_SCENE:
      if (!loadFailsafeScene(frame)) {
        memset(
          frame,
          0,
          sizeof(frame));
        sceneMissing = true;
      }
      break;

    case FAILSAFE_HOLD:
    default:
      shouldSetFrame = false;
      break;
  }

  if (shouldSetFrame) {
    setDmxFrame(
      frame,
      DMX_CHANNEL_COUNT,
      true);
  }

  artnet.setPortOutputActive(false);
  updateMergePollReplyStatus();

  if (sceneMissing) {
    artnet.setNodeReport(
      RcConfigErr,
      "Failsafe scene missing; output zero");
  } else {
    artnet.setNodeReport(
      RcPowerOk,
      getFailsafeModeName(config.failsafeMode));
  }
}

/** @brief Applies and persists a failsafe mode requested through ArtAddress. */
static void setFailsafeModeFromArtAddress(
  FailsafeMode mode) {
  String error;

  const ConfigResult result =
    updateFailsafeMode(
      mode,
      error);

  if (result == ConfigResult::OK) {
    updateFailsafePollReplyStatus();
    artnet.setNodeReport(
      RcPowerOk,
      getFailsafeModeName(mode));
  } else {
    artnet.setNodeReport(
      RcConfigErr,
      "Failsafe mode programming failed");
  }
}

/** @brief Performs a deferred ArtAddress failsafe-scene recording request. */
static void handleFailsafeSceneRecordPending() {
  if (!failsafeSceneRecordPending) {
    return;
  }

  failsafeSceneRecordPending = false;

  String recordError;

  if (recordFailsafeScene(recordError)) {
    artnet.setNodeReport(
      RcPowerOk,
      "Failsafe scene recorded");
  } else {
    artnet.setNodeReport(
      RcConfigErr,
      "Failsafe scene recording failed");
  }
}

/** @brief Applies and persists a merge mode requested through ArtAddress. */
static void setMergeModeFromArtAddress(
  MergeMode mode) {
  String error;

  const ConfigResult result =
    updateMergeMode(
      mode,
      error);

  if (result == ConfigResult::OK) {
    applyMergedOutputFrame();
    updateMergePollReplyStatus();

    artnet.setNodeReport(
      RcPowerOk,
      mode == MERGE_LTP
        ? "Merge mode set to LTP"
        : "Merge mode set to HTP");
  } else {
    artnet.setNodeReport(
      RcConfigErr,
      "Merge mode programming failed");
  }
}

/** @brief Decodes one ArtAddress field whose high bit enables programming. */
static bool decodeArtAddressProgramValue(
  uint8_t value,
  uint8_t mask,
  uint8_t maximum,
  uint8_t& decoded) {
  if ((value & 0x80) == 0) {
    return false;
  }

  decoded = value & mask;
  return decoded <= maximum;
}

/** @brief Applies ArtAddress Net/Sub-Net/SwIn/SwOut programming. */
static bool applyArtAddressPortAddress(
  const ArtAddressInfo& info) {
  uint8_t requestedNet =
    config.net;
  uint8_t requestedSubnet =
    config.subnetId;
  uint8_t requestedUniverse =
    config.universe;

  bool requestedChange = false;

  uint8_t decoded = 0;

  if (decodeArtAddressProgramValue(
        info.netSwitch,
        0x7f,
        127,
        decoded)) {
    requestedNet = decoded;
    requestedChange = true;
  }

  if (decodeArtAddressProgramValue(
        info.subSwitch,
        0x0f,
        15,
        decoded)) {
    requestedSubnet = decoded;
    requestedChange = true;
  }

  const uint8_t portUniverse =
    config.direction == ARTNET_TO_DMX
      ? info.swOut[0]
      : info.swIn[0];

  if (decodeArtAddressProgramValue(
        portUniverse,
        0x0f,
        15,
        decoded)) {
    requestedUniverse = decoded;
    requestedChange = true;
  }

  if (!requestedChange) {
    return false;
  }

  String error;
  const ConfigResult result =
    updateArtNetPortAddress(
      requestedNet,
      requestedSubnet,
      requestedUniverse,
      error);

  if (result != ConfigResult::OK) {
    artnet.setNodeReport(
      RcConfigErr,
      "ArtAddress Port-Address failed");
    return false;
  }

  artnet.setStartingUniverse(
    getConfiguredUniverse());

  artnet.setNodeReport(
    RcPowerOk,
    "ArtAddress Port-Address programmed");

  clearSubscribers();
  clearArtDmxSequences();
  clearArtDmxMerge();
  clearArtSyncState();
  lastSubscriberPollMillis = 0;
  discoveryActive = false;
  artnetActive = false;
  outputFailsafeActive = false;

  if (config.direction == DMX_TO_ARTNET) {
    startArtNetDiscovery();
  }

  return true;
}

/** @brief Clears Art-Net runtime state affected by a physical direction change. */
static void resetArtNetRuntimeForDirectionChange() {
  clearSubscribers();
  clearArtDmxSequences();
  clearArtDmxMerge();
  clearArtSyncState();
  lastSubscriberPollMillis = 0;
  discoveryActive = false;
  artnetActive = false;
  outputFailsafeActive = false;

  artnet.setPortInputActive(false);
  artnet.setPortOutputActive(false);
}

/** @brief Applies and persists an ArtAddress physical port-direction command. */
static void setDirectionFromArtAddress(
  Direction direction) {
  const Direction previousDirection =
    config.direction;

  String error;
  const ConfigResult result =
    updateConfiguredDirection(
      direction,
      error);

  if (result != ConfigResult::OK) {
    LOG_WARN_PRINT("ArtAddress direction rejected: ");
    LOG_PRINTLN(
      LOG_LEVEL_WARN,
      error);

    artnet.setNodeReport(
      RcConfigErr,
      "ArtAddress direction failed");
    return;
  }

  resetArtNetRuntimeForDirectionChange();

  artnet.setDirection(
    config.direction == ARTNET_TO_DMX);
  artnet.setStartingUniverse(
    getConfiguredUniverse());

  updateDirection();

  if (!restartDMX()) {
    artnet.setNodeReport(
      RcDmxError,
      "DMX direction restart failed");
    return;
  }

  if (config.direction == DMX_TO_ARTNET) {
    startArtNetDiscovery();
  }

  artnet.setNodeReport(
    RcPowerOk,
    config.direction == ARTNET_TO_DMX
      ? "Direction set to DMX output"
      : "Direction set to DMX input");

  if (previousDirection != config.direction) {
    LOG_INFO_PRINT("ArtAddress direction changed to ");
    LOG_PRINTLN(
      LOG_LEVEL_INFO,
      config.direction == ARTNET_TO_DMX
        ? "DMX output"
        : "DMX input");
  }
}

bool applyArtNetRuntimeConfig(
  const Config& previous,
  String& error) {
  error = "";

  const bool directionChanged =
    previous.direction != config.direction;
  const bool portAddressChanged =
    previous.net != config.net
    || previous.subnetId != config.subnetId
    || previous.universe != config.universe;
  const bool terminationChanged =
    previous.terminationMode != config.terminationMode;

  if (previous.shortName != config.shortName) {
    artnet.setShortName(
      config.shortName.c_str());
  }

  if (previous.longName != config.longName) {
    artnet.setLongName(
      config.longName.c_str());
  }

  if (previous.legacyArtPollReply
      != config.legacyArtPollReply) {
    artnet.setLegacyArtNet3Mode(
      config.legacyArtPollReply);
  }

  if (previous.failsafeMode
      != config.failsafeMode) {
    updateFailsafePollReplyStatus();

    if (outputFailsafeActive) {
      applyOutputFailsafe();
    }
  }

  if (previous.mergeMode
      != config.mergeMode) {
    applyMergedOutputFrame();
    updateMergePollReplyStatus();
  }

  if (terminationChanged
      && !directionChanged) {
    applyTermination();
  }

  if (directionChanged) {
    resetArtNetRuntimeForDirectionChange();

    artnet.setDirection(
      config.direction == ARTNET_TO_DMX);
    artnet.setStartingUniverse(
      getConfiguredUniverse());

    updateDirection();

    if (!restartDMX()) {
      error = "DMX direction restart failed";
      artnet.setNodeReport(
        RcDmxError,
        error.c_str());
      return false;
    }

    if (config.direction == DMX_TO_ARTNET) {
      startArtNetDiscovery();
    }

    artnet.setNodeReport(
      RcPowerOk,
      config.direction == ARTNET_TO_DMX
        ? "Direction set to DMX output"
        : "Direction set to DMX input");
  } else if (portAddressChanged) {
    artnet.setStartingUniverse(
      getConfiguredUniverse());

    clearSubscribers();
    clearArtDmxSequences();
    clearArtDmxMerge();
    clearArtSyncState();
    lastSubscriberPollMillis = 0;
    discoveryActive = false;
    artnetActive = false;
    outputFailsafeActive = false;

    if (config.direction == DMX_TO_ARTNET) {
      startArtNetDiscovery();
    }

    artnet.setNodeReport(
      RcPowerOk,
      "Port-Address changed");
  }

  updateFailsafePollReplyStatus();
  updateMergePollReplyStatus();

  LOG_INFO("Art-Net runtime configuration applied live");
  return true;
}

/** @brief Populates an ArtIpProgReply from the current uNode network state. */
static void fillArtIpProgReply(
  ArtIpProgReplyInfo& reply) {
  reply.port = ARTNET_PORT;
  reply.dhcp =
    config.wifiMode != WIFI_MODE_AP
    && config.dhcp;

  if (config.wifiMode == WIFI_MODE_AP) {
    reply.ip = WiFi.softAPIP();
    reply.subnet = IPAddress(255, 255, 255, 0);
    reply.gateway = WiFi.softAPIP();
    reply.dhcp = false;
    return;
  }

  if (config.dhcp
      && WiFi.status() == WL_CONNECTED) {
    reply.ip = WiFi.localIP();
    reply.subnet = WiFi.subnetMask();
    reply.gateway = WiFi.gatewayIP();
    return;
  }

  reply.ip = parseConfigAddress(
    config.ip,
    WiFi.status() == WL_CONNECTED
      ? WiFi.localIP()
      : IPAddress());
  reply.subnet = parseConfigAddress(
    config.subnet,
    WiFi.status() == WL_CONNECTED
      ? WiFi.subnetMask()
      : IPAddress(255, 255, 255, 0));
  reply.gateway = parseConfigAddress(
    config.gateway,
    WiFi.status() == WL_CONNECTED
      ? WiFi.gatewayIP()
      : IPAddress());
}

/** @brief Stores an ArtIpProg request and schedules a restart when needed. */
static bool onArtIpProg(
  const ArtIpProgInfo& info,
  ArtIpProgReplyInfo& reply) {
  fillArtIpProgReply(reply);

  const bool programmingEnabled =
    (info.command & ARTNET_IP_PROG_COMMAND_ENABLE) != 0;
  const bool enquiryOnly =
    !programmingEnabled
    || (info.command & 0x7f) == 0;

  if (enquiryOnly) {
    artnet.setNodeReport(
      RcPowerOk,
      "ArtIpProg enquiry");
    return true;
  }

  const bool previousDhcp = config.dhcp;
  const String previousIp = config.ip;
  const String previousSubnet = config.subnet;
  const String previousGateway = config.gateway;

  const bool enableDhcp =
    (info.command & ARTNET_IP_PROG_COMMAND_DHCP) != 0;
  const bool restoreDefaults =
    !enableDhcp
    && (info.command & ARTNET_IP_PROG_COMMAND_DEFAULTS) != 0;
  const bool programIp =
    !enableDhcp
    && !restoreDefaults
    && (info.command & ARTNET_IP_PROG_COMMAND_IP) != 0;
  const bool programSubnet =
    !enableDhcp
    && !restoreDefaults
    && (info.command & ARTNET_IP_PROG_COMMAND_SUBNET) != 0;
  const bool programGateway =
    !enableDhcp
    && !restoreDefaults
    && (info.command & ARTNET_IP_PROG_COMMAND_GATEWAY) != 0;

  if ((info.command & ARTNET_IP_PROG_COMMAND_PORT) != 0) {
    LOG_DEBUG("Ignoring deprecated ArtIpProg port field");
  }

  String error;
  const ConfigResult result =
    updateNetworkFromArtIpProg(
      enableDhcp,
      restoreDefaults,
      programIp,
      info.ip,
      programSubnet,
      info.subnet,
      programGateway,
      info.gateway,
      error);

  if (result != ConfigResult::OK) {
    LOG_WARN_PRINT("ArtIpProg rejected: ");
    LOG_PRINTLN(
      LOG_LEVEL_WARN,
      error);

    artnet.setNodeReport(
      RcConfigErr,
      "ArtIpProg rejected");
    fillArtIpProgReply(reply);
    return false;
  }

  fillArtIpProgReply(reply);
  artnet.isDHCP(reply.dhcp);

  const bool changed =
    previousDhcp != config.dhcp
    || previousIp != config.ip
    || previousSubnet != config.subnet
    || previousGateway != config.gateway;

  if (changed) {
    artIpProgRestartPending = true;
    artIpProgRestartMillis =
      millis() + ART_IP_PROG_RESTART_DELAY_MS;

    artnet.setNodeReport(
      RcPowerOk,
      "ArtIpProg programmed; restart pending");

    LOG_INFO("ArtIpProg stored network settings; restart pending");
  } else {
    artnet.setNodeReport(
      RcPowerOk,
      "ArtIpProg no change");
  }

  return true;
}

/** @brief Clears remembered ArtDmx sequence state for all senders. */
static void clearArtDmxSequences() {
  for (uint8_t i = 0; i < MAX_ARTDMX_SEQUENCE_SOURCES; i++) {
    artDmxSequences[i].active = false;
  }
}

/** @brief Clears ArtDmx merge buffers, cancel state, and merge advertisement. */
static void clearArtDmxMerge() {
  for (uint8_t i = 0; i < 2; i++) {
    mergeSources[i].active = false;
    mergeSources[i].lastMillis = 0;
  }

  lastMergeSourceIndex = 0;
  cancelMergePending = false;
  mergeLockedToSingleSource = false;
  mergeLockIP = IPAddress();
  mergeLockPhysical = 0;
  artnet.setPortOutputMergeStatus(
    false,
    config.mergeMode == MERGE_LTP);
}

/** @brief Clears ArtSync buffering state. */
static void clearArtSyncState() {
  artSyncActive = false;
  artSyncPendingOutput = false;
  lastArtSyncMillis = 0;
}

/** @return Index of the matching, free, or oldest ArtDmx sequence slot. */
static uint8_t getArtDmxSequenceSlot(
  const IPAddress& senderIP,
  uint8_t physical,
  uint32_t now,
  bool& matched) {
  matched = false;
  uint8_t selected = 0;
  uint32_t oldestAge = 0;

  for (uint8_t i = 0; i < MAX_ARTDMX_SEQUENCE_SOURCES; i++) {
    ArtDmxSequenceState& state =
      artDmxSequences[i];

    if (state.active
        && state.senderIP == senderIP
        && state.physical == physical) {
      matched = true;
      return i;
    }

    if (!state.active) {
      return i;
    }

    const uint32_t age =
      now - state.lastMillis;

    if (age >= oldestAge) {
      oldestAge = age;
      selected = i;
    }
  }

  return selected;
}

/** @return True when an ArtDmx sequence is disabled, new, or newer. */
static bool acceptArtDmxSequence(
  uint8_t sequence) {
  const IPAddress senderIP =
    artnet.getSenderIp();
  const uint8_t physical =
    artnet.getIncomingPhysical();

  if (sequence == 0) {
    for (uint8_t i = 0; i < MAX_ARTDMX_SEQUENCE_SOURCES; i++) {
      if (artDmxSequences[i].active
          && artDmxSequences[i].senderIP == senderIP
          && artDmxSequences[i].physical == physical) {
        artDmxSequences[i].active = false;
        break;
      }
    }

    return true;
  }

  const uint32_t now =
    millis();

  bool matched = false;
  const uint8_t index =
    getArtDmxSequenceSlot(
      senderIP,
      physical,
      now,
      matched);

  ArtDmxSequenceState& state =
    artDmxSequences[index];

  if (matched
      && now - state.lastMillis <= ARTDMX_SEQUENCE_TIMEOUT_MS) {
    const uint8_t delta =
      sequence - state.sequence;

    if (delta == 0 || delta > 127) {
      sequenceDropCounter++;
      LOG_DEBUG_PRINT("Dropped out-of-order ArtDmx from ");
      LOG_PRINT(LOG_LEVEL_DEBUG, senderIP);
      LOG_PRINT(LOG_LEVEL_DEBUG, " seq=");
      LOG_PRINT(LOG_LEVEL_DEBUG, sequence);
      LOG_PRINT(LOG_LEVEL_DEBUG, " last=");
      LOG_PRINTLN(LOG_LEVEL_DEBUG, state.sequence);
      return false;
    }
  }

  state.senderIP = senderIP;
  state.physical = physical;
  state.sequence = sequence;
  state.lastMillis = now;
  state.active = true;

  return true;
}

/** @return True when one merge source matches the current ArtDmx sender. */
static bool isCurrentMergeSource(
  const ArtDmxMergeSource& source) {
  return source.active
         && source.senderIP == artnet.getSenderIp()
         && source.physical == artnet.getIncomingPhysical();
}

/** @return Number of currently active ArtDmx merge sources. */
static uint8_t getActiveMergeSourceCount() {
  uint8_t count = 0;

  for (uint8_t i = 0; i < 2; i++) {
    if (mergeSources[i].active) {
      count++;
    }
  }

  return count;
}

/** @brief Updates ArtPollReply merge-state and merge-mode bits. */
static void updateMergePollReplyStatus() {
  artnet.setPortOutputMergeStatus(
    getActiveMergeSourceCount() >= 2,
    config.mergeMode == MERGE_LTP);
}

/** @brief Copies one ArtDmx payload into a 512-channel merge source buffer. */
static void updateMergeSourceFrame(
  ArtDmxMergeSource& source,
  const uint8_t* data,
  uint16_t length,
  uint32_t now) {
  length =
    min(
      length,
      (uint16_t)DMX_CHANNEL_COUNT);

  memcpy(
    source.frame,
    data,
    length);

  if (length < DMX_CHANNEL_COUNT) {
    memset(
      source.frame + length,
      0,
      DMX_CHANNEL_COUNT - length);
  }

  source.senderIP =
    artnet.getSenderIp();
  source.physical =
    artnet.getIncomingPhysical();
  source.lastMillis = now;
  source.active = true;
}

/** @return Index of a matching, free, or unavailable ArtDmx merge slot. */
static int8_t getMergeSourceSlot() {
  int8_t freeSlot = -1;

  for (uint8_t i = 0; i < 2; i++) {
    if (isCurrentMergeSource(mergeSources[i])) {
      return i;
    }

    if (!mergeSources[i].active
        && freeSlot < 0) {
      freeSlot = i;
    }
  }

  return freeSlot;
}

/** @brief Applies the configured merge mode to the shared DMX frame. */
static void applyMergedOutputFrame() {
  static uint8_t mergedFrame[DMX_CHANNEL_COUNT];

  const uint8_t activeCount =
    getActiveMergeSourceCount();

  if (activeCount == 0) {
    return;
  }

  if (activeCount == 1) {
    const uint8_t sourceIndex =
      mergeSources[0].active ? 0 : 1;

    setDmxFrame(
      mergeSources[sourceIndex].frame,
      DMX_CHANNEL_COUNT,
      true);
    updateMergePollReplyStatus();
    return;
  }

  if (config.mergeMode == MERGE_LTP) {
    setDmxFrame(
      mergeSources[lastMergeSourceIndex].frame,
      DMX_CHANNEL_COUNT,
      true);
    updateMergePollReplyStatus();
    return;
  }

  for (uint16_t channel = 0;
       channel < DMX_CHANNEL_COUNT;
       channel++) {
    mergedFrame[channel] =
      max(
        mergeSources[0].frame[channel],
        mergeSources[1].frame[channel]);
  }

  setDmxFrame(
    mergedFrame,
    DMX_CHANNEL_COUNT,
    true);
  updateMergePollReplyStatus();
}

/** @brief Expires stale ArtDmx merge sources after the Art-Net timeout. */
static void expireStaleMergeSources(
  uint32_t now) {
  if (config.direction != ARTNET_TO_DMX) {
    return;
  }

  bool removed = false;

  for (uint8_t i = 0; i < 2; i++) {
    if (mergeSources[i].active
        && now - mergeSources[i].lastMillis
            >= ARTDMX_MERGE_SOURCE_TIMEOUT_MS) {
      LOG_INFO_PRINT("ArtDmx merge source expired: ");
      LOG_PRINT(LOG_LEVEL_INFO, mergeSources[i].senderIP);
      LOG_PRINT(LOG_LEVEL_INFO, " physical=");
      LOG_PRINTLN(LOG_LEVEL_INFO, mergeSources[i].physical);
      mergeSources[i].active = false;
      removed = true;
    }
  }

  if (!removed) {
    return;
  }

  if (getActiveMergeSourceCount() == 0) {
    mergeLockedToSingleSource = false;
    mergeLockIP = IPAddress();
    mergeLockPhysical = 0;
  }

  if (lastMergeSourceIndex == 0
      && !mergeSources[0].active
      && mergeSources[1].active) {
    lastMergeSourceIndex = 1;
  } else if (lastMergeSourceIndex == 1
             && !mergeSources[1].active
             && mergeSources[0].active) {
    lastMergeSourceIndex = 0;
  }

  applyMergedOutputFrame();
  updateMergePollReplyStatus();
}

/** @brief Applies one accepted ArtDmx packet to source buffers and output. */
static bool applyArtDmxToMerge(
  const uint8_t* data,
  uint16_t length,
  bool applyOutput) {
  const uint32_t now =
    millis();

  if (mergeLockedToSingleSource
      && getActiveMergeSourceCount() > 0
      && (artnet.getSenderIp() != mergeLockIP
          || artnet.getIncomingPhysical()
             != mergeLockPhysical)) {
    mergeLockDropCounter++;
    LOG_WARN_PRINT("Ignoring ArtDmx after AcCancelMerge lock: ");
    LOG_PRINT(LOG_LEVEL_WARN, artnet.getSenderIp());
    LOG_PRINT(LOG_LEVEL_WARN, " physical=");
    LOG_PRINT(LOG_LEVEL_WARN, artnet.getIncomingPhysical());
    LOG_PRINT(LOG_LEVEL_WARN, " locked=");
    LOG_PRINT(LOG_LEVEL_WARN, mergeLockIP);
    LOG_PRINT(LOG_LEVEL_WARN, " physical=");
    LOG_PRINTLN(LOG_LEVEL_WARN, mergeLockPhysical);
    return false;
  }

  if (mergeLockedToSingleSource
      && getActiveMergeSourceCount() == 0) {
    mergeLockedToSingleSource = false;
    mergeLockIP = IPAddress();
    mergeLockPhysical = 0;
  }

  int8_t index =
    getMergeSourceSlot();

  if (cancelMergePending) {
    const IPAddress lockedIP =
      artnet.getSenderIp();
    const uint8_t lockedPhysical =
      artnet.getIncomingPhysical();
    clearArtDmxMerge();
    mergeLockedToSingleSource = true;
    mergeLockIP = lockedIP;
    mergeLockPhysical = lockedPhysical;
    index = 0;
  }

  if (index < 0) {
    mergeThirdSourceDropCounter++;
    LOG_WARN_PRINT("Ignoring third ArtDmx merge source: ");
    LOG_PRINT(LOG_LEVEL_WARN, artnet.getSenderIp());
    LOG_PRINT(LOG_LEVEL_WARN, " physical=");
    LOG_PRINTLN(LOG_LEVEL_WARN, artnet.getIncomingPhysical());
    return false;
  }

  updateMergeSourceFrame(
    mergeSources[index],
    data,
    length,
    now);

  lastMergeSourceIndex = index;
  cancelMergePending = false;

  if (applyOutput) {
    applyMergedOutputFrame();
  }

  return true;
}

/**
 * @brief Accepts ArtDmx for the configured Port-Address and updates DMX output.
 * @param universe Received 15-bit Port-Address.
 * @param length Number of DMX data slots.
 * @param sequence ArtDmx sequence value.
 * @param data Pointer to the received payload.
 */
static void onDmxFrame(
  uint16_t universe,
  uint16_t length,
  uint8_t sequence,
  uint8_t* data) {
  uint16_t configuredUniverse =
    getConfiguredUniverse();

  if (universe != configuredUniverse) {
    wrongUniverseCounter++;
    lastWrongUniverse = universe;
    lastWrongUniverseMillis =
      millis();
    return;
  }

  if (config.direction != ARTNET_TO_DMX) {
    directionDropCounter++;
    return;
  }

  if (!acceptArtDmxSequence(sequence)) {
    return;
  }

  if (length > 512) {
    length = 512;
  }

  if (!applyArtDmxToMerge(
        data,
        length,
        !artSyncActive)) {
    return;
  }

  if (artSyncActive) {
    artSyncPendingOutput = true;
  }

  LOG_TRACE_PRINT("ArtDmx CH1=");
  LOG_PRINT(LOG_LEVEL_TRACE, getDmxChannel(0));

  LOG_TRACE_PRINT(" CH2=");
  LOG_PRINTLN(LOG_LEVEL_TRACE, getDmxChannel(1));

  LOG_TRACE_PRINT("Heap=");
  LOG_PRINTLN(LOG_LEVEL_TRACE, ESP.getFreeHeap());

  artDmxCounter++;

  fpsCounter++;

  lastArtNetPacketMillis =
    millis();

  artnetActive = true;
  outputFailsafeActive = false;

  if (!artSyncActive) {
    artnet.setPortOutputActive(true);
    flashDMXOutputLED();
  }
}

/** @brief Flushes pending ArtDmx data when an ArtSync packet is received. */
static void onArtSync() {
  if (config.direction != ARTNET_TO_DMX) {
    return;
  }

  artSyncActive = true;
  lastArtSyncMillis =
    millis();
  artSyncCounter++;

  if (!artSyncPendingOutput) {
    LOG_TRACE("ArtSync received without pending ArtDmx");
    return;
  }

  applyMergedOutputFrame();
  artSyncPendingOutput = false;

  artnet.setPortOutputActive(true);
  flashDMXOutputLED();

  LOG_TRACE("ArtSync flushed pending ArtDmx");
}

/** @brief Advances the subscriber-set version while reserving zero. */
static void markSubscriberListChanged() {
  subscriberVersion++;

  if (subscriberVersion == 0) {
    subscriberVersion = 1;
  }
}

/** @brief Removes one subscriber and compacts the fixed-size array. */
static void removeSubscriber(uint8_t index) {
  if (index >= subscriberCount) {
    return;
  }

  LOG_DEBUG_PRINT("Art-Net subscriber expired: ");
  LOG_PRINTLN(
    LOG_LEVEL_DEBUG,
    subscribers[index].ip);

  for (uint8_t i = index; i + 1 < subscriberCount; i++) {
    subscribers[i] = subscribers[i + 1];
  }

  subscriberCount--;
  markSubscriberListChanged();
}

static void clearSubscribers() {
  if (subscriberCount > 0) {
    subscriberCount = 0;
    markSubscriberListChanged();
  }
}

/** @return Full 15-bit Port-Address reconstructed from a PollReply nibble. */
static uint16_t getReplyPortAddress(
  const ArtPollReplyInfo& info,
  uint8_t sw) {
  return ((uint16_t)info.netSwitch << 8)
         | ((uint16_t)info.subSwitch << 4)
         | (sw & 0x0f);
}

/** @brief Updates subscriber state from a parsed ArtPollReply. */
static void onArtPollReply(
  const ArtPollReplyInfo& info) {
  if (config.direction != DMX_TO_ARTNET
      || info.senderIP == WiFi.localIP()
      || info.senderIP == WiFi.softAPIP()) {
    return;
  }

  const uint16_t configuredUniverse =
    getConfiguredUniverse();
  uint8_t inputPortMask = 0;
  uint8_t outputPortMask = 0;

  for (uint8_t port = 0; port < info.numPorts; port++) {
    if ((info.portTypes[port] & 0x40)
        && getReplyPortAddress(info, info.swIn[port])
            == configuredUniverse) {
      inputPortMask |= 1 << port;
    }

    if ((info.portTypes[port] & 0x80)
        && getReplyPortAddress(info, info.swOut[port])
            == configuredUniverse) {
      outputPortMask |= 1 << port;
    }
  }

  uint8_t index = subscriberCount;

  for (uint8_t i = 0; i < subscriberCount; i++) {
    if (subscribers[i].ip == info.senderIP
        && subscribers[i].bindIndex == info.bindIndex) {
      index = i;
      break;
    }
  }

  if (inputPortMask == 0 && outputPortMask == 0) {
    if (index < subscriberCount) {
      removeSubscriber(index);
    }

    return;
  }

  if (index == subscriberCount) {
    if (subscriberCount >= MAX_ARTNET_SUBSCRIBERS) {
      LOG_WARN("Art-Net subscriber list full");
      return;
    }

    subscriberCount++;
    markSubscriberListChanged();

    LOG_INFO_PRINT("Art-Net subscriber found: ");
    LOG_PRINTLN(
      LOG_LEVEL_INFO,
      info.senderIP);
  }

  subscribers[index].ip = info.senderIP;
  subscribers[index].bindIndex = info.bindIndex;
  subscribers[index].inputPortMask = inputPortMask;
  subscribers[index].outputPortMask = outputPortMask;
  subscribers[index].lastSeenMillis = millis();

  strncpy(
    subscribers[index].name,
    info.portName,
    sizeof(subscribers[index].name) - 1);

  subscribers[index]
    .name[sizeof(subscribers[index].name) - 1] = '\0';

  for (size_t i = 0;
       i < sizeof(subscribers[index].name) - 1
       && subscribers[index].name[i] != '\0';
       i++) {
    const uint8_t c =
      subscribers[index].name[i];

    if (c < 32 || c > 126) {
      subscribers[index].name[i] = '?';
    }
  }
}

/** @brief Applies supported ArtAddress names and indicator commands. */
static void onArtAddress(
  const ArtAddressInfo& info) {
  bool portNameChanged = false;
  bool longNameChanged = false;
  String error;
  bool portAddressChanged = false;

  const ConfigResult nameResult =
    updateArtNetNames(
      info.portName,
      info.longName,
      portNameChanged,
      longNameChanged,
      error);

  if (nameResult == ConfigResult::OK) {
    if (portNameChanged) {
      artnet.setShortName(config.shortName.c_str());
    }

    if (longNameChanged) {
      artnet.setLongName(config.longName.c_str());
    }

    if (portNameChanged || longNameChanged) {
      artnet.setNodeReport(
        longNameChanged ? RcLoNameOk : RcShNameOk,
        longNameChanged
          ? "ArtAddress long name programmed"
          : "ArtAddress port name programmed");
    }
  } else {
    artnet.setNodeReport(
      RcConfigErr,
      "ArtAddress name programming failed");
  }

  portAddressChanged =
    applyArtAddressPortAddress(
      info);

  switch (info.command) {
    case ARTNET_AC_LED_NORMAL:
      artnet.setIndicatorState(
        ArtNetIndicatorState::NORMAL);
      setLedIndicatorMode(
        INDICATORS_NORMAL);
      break;

    case ARTNET_AC_LED_MUTE:
      artnet.setIndicatorState(
        ArtNetIndicatorState::MUTE);
      setLedIndicatorMode(
        INDICATORS_MUTE);
      break;

    case ARTNET_AC_LED_LOCATE:
      artnet.setIndicatorState(
        ArtNetIndicatorState::LOCATE);
      setLedIndicatorMode(
        INDICATORS_LOCATE);
      break;

    case ARTNET_AC_CANCEL_MERGE:
      cancelMergePending = true;
      artnet.setNodeReport(
        RcPowerOk,
        "Cancel merge pending");
      break;

    case ARTNET_AC_FAIL_HOLD:
      setFailsafeModeFromArtAddress(
        FAILSAFE_HOLD);
      break;

    case ARTNET_AC_FAIL_ZERO:
      setFailsafeModeFromArtAddress(
        FAILSAFE_ZERO);
      break;

    case ARTNET_AC_FAIL_FULL:
      setFailsafeModeFromArtAddress(
        FAILSAFE_FULL);
      break;

    case ARTNET_AC_FAIL_SCENE:
      setFailsafeModeFromArtAddress(
        FAILSAFE_SCENE);
      break;

    case ARTNET_AC_FAIL_RECORD:
      failsafeSceneRecordPending = true;
      artnet.setNodeReport(
        RcPowerOk,
        "Failsafe scene record pending");
      break;

    case ARTNET_AC_MERGE_LTP_0:
      setMergeModeFromArtAddress(
        MERGE_LTP);
      break;

    case ARTNET_AC_MERGE_HTP_0:
      setMergeModeFromArtAddress(
        MERGE_HTP);
      break;

    case ARTNET_AC_DIRECTION_TX_0:
      setDirectionFromArtAddress(
        ARTNET_TO_DMX);
      break;

    case ARTNET_AC_DIRECTION_RX_0:
      setDirectionFromArtAddress(
        DMX_TO_ARTNET);
      break;

    default:
      break;
  }

  (void)portAddressChanged;
}

bool initArtNet() {
  LOG_SECTION("Art-Net Init");

  artnetSocketReady =
    artnet.begin(config.hostname) == 0;

  if (!artnetSocketReady) {
    nextArtNetBindRetryMillis =
      millis() + ARTNET_BIND_RETRY_MS;
    LOG_WARN("Art-Net UDP bind failed");
  }

  artnet.setShortName(
    config.shortName.c_str());

  artnet.setLongName(
    config.longName.c_str());

  artnet.setNodeReport(
    RcPowerOk,
    "uNode Ready");

  artnet.setFirmwareVersion(
    FW_VERSION_MAJOR,
    FW_VERSION_MINOR);

  artnet.setDirection(
    config.direction == ARTNET_TO_DMX);

  artnet.isDHCP(
    config.wifiMode != WIFI_MODE_AP
    && config.dhcp
    && WiFi.status() == WL_CONNECTED);

  artnet.setLegacyArtNet3Mode(
    config.legacyArtPollReply);

  updateMergePollReplyStatus();

  artnet.setStartingUniverse(
    getConfiguredUniverse());

  updateFailsafePollReplyStatus();

  artnet.setArtDmxCallback(
    onDmxFrame);

  artnet.setArtSyncCallback(
    onArtSync);

  artnet.setArtPollReplyCallback(
    onArtPollReply);

  artnet.setArtAddressCallback(
    onArtAddress);

  artnet.setArtIpProgCallback(
    onArtIpProg);

  fpsTimer =
    millis();

  updateDirection();

  LOG_INFO_PRINT("ShortName: ");
  LOG_PRINTLN(LOG_LEVEL_INFO, config.shortName);

  LOG_DEBUG_PRINT("LongName: ");
  LOG_PRINTLN(LOG_LEVEL_DEBUG, config.longName);

  LOG_INFO_PRINT("Net: ");
  LOG_PRINTLN(LOG_LEVEL_INFO, config.net);

  LOG_INFO_PRINT("Subnet: ");
  LOG_PRINTLN(LOG_LEVEL_INFO, config.subnetId);

  LOG_INFO_PRINT("Universe: ");
  LOG_PRINTLN(LOG_LEVEL_INFO, config.universe);

  if (artnetSocketReady
      && config.direction == DMX_TO_ARTNET) {
    startArtNetDiscovery();
  }

  return artnetSocketReady;
}

void updateArtNet() {
  uint32_t now = millis();

  if (!artnetSocketReady) {
    if ((int32_t)(now - nextArtNetBindRetryMillis) >= 0) {
      artnetSocketReady =
        artnet.begin(config.hostname) == 0;
      nextArtNetBindRetryMillis =
        now + ARTNET_BIND_RETRY_MS;

      if (artnetSocketReady) {
        LOG_INFO("Art-Net UDP bind restored");

        clearSubscribers();
        clearArtDmxSequences();
        clearArtSyncState();
        artnet.isDHCP(
          config.wifiMode != WIFI_MODE_AP
          && config.dhcp
          && WiFi.status() == WL_CONNECTED);
        if (config.direction == DMX_TO_ARTNET) {
          startArtNetDiscovery();
        }
      }
    }

    return;
  }

  const uint16_t opcode = artnet.read();
  now = millis();

  handleFailsafeSceneRecordPending();

  if (opcode != 0
      && opcode != OpDmx
      && opcode != OpNzs) {
    flashArtNetLED();
  }

  if (artIpProgRestartPending
      && (int32_t)(now - artIpProgRestartMillis) >= 0) {
    LOG_INFO("Restarting after ArtIpProg");
    delay(50);
    ESP.restart();
  }

  if (now - fpsTimer >= 1000) {
    currentFPS =
      fpsCounter;

    fpsCounter = 0;

    fpsTimer = now;
  }

  if (artnetActive) {
    if (now - lastArtNetPacketMillis > ARTNET_OUTPUT_TIMEOUT_MS) {
      artnetActive = false;
      applyOutputFailsafe();
    }
  }

  if (artSyncActive
      && now - lastArtSyncMillis >= ARTSYNC_TIMEOUT_MS) {
    artSyncActive = false;
    artSyncTimeoutCounter++;

    if (artSyncPendingOutput) {
      applyMergedOutputFrame();
      artSyncPendingOutput = false;
      artnet.setPortOutputActive(true);
      flashDMXOutputLED();
    }

    LOG_INFO("ArtSync timeout; returning to asynchronous ArtDmx output");
  }

  expireStaleMergeSources(now);

  if (config.direction == DMX_TO_ARTNET
      && now - lastSubscriberPollMillis
          >= SUBSCRIBER_POLL_INTERVAL_MS) {
    if (artnet.sendArtPoll(getArtNetBroadcast())) {
      lastSubscriberPollMillis = now;
    }
  }

  for (uint8_t i = 0; i < subscriberCount;) {
    if (now - subscribers[i].lastSeenMillis
        >= SUBSCRIBER_TIMEOUT_MS) {
      removeSubscriber(i);
    } else {
      i++;
    }
  }

  if (discoveryActive
      && now - discoveryStartedMillis
          >= DISCOVERY_DURATION_MS) {
    discoveryActive = false;
  }
}

void handleArtNetNetworkChange() {
  LOG_INFO("Art-Net network interface changed");

  clearSubscribers();
  clearArtDmxSequences();
  clearArtSyncState();
  lastSubscriberPollMillis = 0;

  artnetSocketReady =
    artnet.begin(config.hostname) == 0;
  artnet.isDHCP(
    config.wifiMode != WIFI_MODE_AP
    && config.dhcp
    && WiFi.status() == WL_CONNECTED);

  artnet.setLegacyArtNet3Mode(
    config.legacyArtPollReply);

  if (artnetSocketReady) {
    if (config.direction == DMX_TO_ARTNET) {
      startArtNetDiscovery();
    }
  } else {
    nextArtNetBindRetryMillis =
      millis() + ARTNET_BIND_RETRY_MS;
  }
}

void updateDirection() {
  applyHardwareForDirection();
}

IPAddress getArtNetBroadcast() {
  IPAddress ip;
  IPAddress mask;

  if (WiFi.status() == WL_CONNECTED) {
    ip = WiFi.localIP();
    mask = WiFi.subnetMask();
  } else {
    ip = WiFi.softAPIP();
    mask = IPAddress(
      255, 255, 255, 0);
  }

  return IPAddress(
    (uint32_t)ip | ~(uint32_t)mask);
}

void startArtNetDiscovery() {
  if (!artnetSocketReady) {
    return;
  }

  discoveryActive = true;
  discoveryStartedMillis = millis();

  if (artnet.sendArtPoll(getArtNetBroadcast())) {
    lastSubscriberPollMillis = millis();
  }

  flashArtNetLED();
}

bool isArtNetDiscoveryActive() {
  return discoveryActive;
}

uint8_t getArtNetSubscriberCount() {
  return subscriberCount;
}

bool getArtNetSubscriber(
  uint8_t index,
  ArtNetSubscriberInfo& subscriber) {
  if (index >= subscriberCount) {
    return false;
  }

  subscriber = subscribers[index];
  return true;
}

uint32_t getArtNetSubscriberVersion() {
  return subscriberVersion;
}

uint32_t getLastSubscriberPollMillis() {
  return lastSubscriberPollMillis;
}

bool sendArtNetFrame() {
  if (!artnetSocketReady) {
    return false;
  }

  artnet.setUniverse(
    getConfiguredUniverse());

  const uint16_t length =
    constrain(
      getDmxFrameLength(),
      (uint16_t)2,
      (uint16_t)DMX_CHANNEL_COUNT);

  artnet.setLength(length);

  for (uint16_t i = 0; i < length; i++) {
    artnet.setByte(
      i,
      getDmxChannel(i));
  }

  IPAddress targets[MAX_ARTNET_SUBSCRIBERS];
  uint8_t targetCount = 0;

  for (uint8_t i = 0; i < subscriberCount; i++) {
    bool duplicate = false;

    for (uint8_t target = 0; target < targetCount; target++) {
      if (targets[target] == subscribers[i].ip) {
        duplicate = true;
        break;
      }
    }

    if (!duplicate) {
      targets[targetCount++] = subscribers[i].ip;
    }
  }

  if (targetCount == 0) {
    return false;
  }

  const bool sent =
    artnet.write(targets, targetCount) > 0;

  if (sent) {
    flashArtNetLED();
  }

  return sent;
}

uint32_t getArtDmxCounter() {
  return artDmxCounter;
}

uint32_t getArtNetFPS() {
  return currentFPS;
}

uint32_t getLastArtNetPacketAge() {
  if (!lastArtNetPacketMillis) {
    return 0;
  }

  return millis() - lastArtNetPacketMillis;
}

uint32_t getArtSyncCounter() {
  return artSyncCounter;
}

uint32_t getLastArtSyncAge() {
  if (!lastArtSyncMillis) {
    return 0;
  }

  return millis() - lastArtSyncMillis;
}

bool isArtSyncActive() {
  return artSyncActive;
}

bool isArtSyncPendingOutput() {
  return artSyncPendingOutput;
}

uint32_t getArtNetOversizedPacketCount() {
  return artnet.getParserDiagnostics().oversizedPackets;
}

uint32_t getArtNetShortPacketCount() {
  return artnet.getParserDiagnostics().shortPackets;
}

uint32_t getArtNetInvalidIdPacketCount() {
  return artnet.getParserDiagnostics().invalidIdPackets;
}

uint32_t getArtNetUnsupportedProtocolCount() {
  return artnet.getParserDiagnostics().unsupportedProtocolPackets;
}

uint32_t getArtNetMalformedPacketCount() {
  return artnet.getParserDiagnostics().malformedPackets;
}

uint32_t getArtNetUnsupportedOpcodeCount() {
  return artnet.getParserDiagnostics().unsupportedOpcodes;
}

uint32_t getArtNetWrongUniverseCount() {
  return wrongUniverseCounter;
}

uint16_t getArtNetLastWrongUniverse() {
  return lastWrongUniverse;
}

uint32_t getArtNetLastWrongUniverseAge() {
  if (!lastWrongUniverseMillis) {
    return 0;
  }

  return millis() - lastWrongUniverseMillis;
}

bool isArtNetWrongUniverseWarningActive() {
  if (!lastWrongUniverseMillis
      || config.direction != ARTNET_TO_DMX) {
    return false;
  }

  const uint32_t now =
    millis();

  return now - lastWrongUniverseMillis < WRONG_UNIVERSE_WARNING_MS
         && (lastArtNetPacketMillis == 0
             || lastWrongUniverseMillis > lastArtNetPacketMillis);
}

uint32_t getArtNetDirectionDropCount() {
  return directionDropCounter;
}

uint32_t getArtNetSequenceDropCount() {
  return sequenceDropCounter;
}

uint32_t getArtNetMergeLockDropCount() {
  return mergeLockDropCounter;
}

uint32_t getArtNetMergeThirdSourceDropCount() {
  return mergeThirdSourceDropCounter;
}

uint32_t getArtNetSyncTimeoutCount() {
  return artSyncTimeoutCounter;
}

uint8_t getArtNetSourceCount() {
  return getActiveMergeSourceCount();
}

bool getArtNetSource(
  uint8_t index,
  ArtNetSourceInfo& source) {
  uint8_t activeIndex = 0;

  for (uint8_t i = 0; i < 2; i++) {
    if (!mergeSources[i].active) {
      continue;
    }

    if (activeIndex == index) {
      source.ip =
        mergeSources[i].senderIP;
      source.physical =
        mergeSources[i].physical;
      source.lastSeenMillis =
        mergeSources[i].lastMillis;
      source.active = true;
      source.winning =
        getActiveMergeSourceCount() == 1
        || config.mergeMode == MERGE_HTP
        || i == lastMergeSourceIndex;
      return true;
    }

    activeIndex++;
  }

  source.active = false;
  source.winning = false;
  return false;
}

uint32_t getArtPollCount() {
  return artnet.getPollCount();
}

uint32_t getLastArtPollMillis() {
  return artnet.getLastPollMillis();
}

bool isArtNetActive() {
  return artnetActive;
}

bool isOutputFailsafeActive() {
  return outputFailsafeActive;
}

void toggleArtNetLocate() {
  const bool enabled =
    artnet.getIndicatorState()
      != ArtNetIndicatorState::LOCATE;

  artnet.setIndicatorState(
    enabled
      ? ArtNetIndicatorState::LOCATE
      : ArtNetIndicatorState::NORMAL);
  setLedIndicatorMode(
    enabled
      ? INDICATORS_LOCATE
      : INDICATORS_NORMAL);
}

bool isSquawking() {
  return artnet.isSquawking();
}
