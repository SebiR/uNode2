#include "websocket.h"

#include "config.h"
#include "artnet.h"
#include "sacn.h"
#include "dmx_frame.h"
#include "dmx.h"
#include "network.h"
#include "leds.h"

#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <ESP8266WiFi.h>

#undef LOG_MODULE
#define LOG_MODULE "WS"

static WebSocketsServer ws(81);

static uint32_t lastBroadcast = 0;
static bool ledStatusInitialized = false;
static StatusLedColor lastNetworkLedColor =
  StatusLedColor::OFF;
static StatusLedColor lastActivityLedColor =
  StatusLedColor::OFF;

/** @return CSS color string matching one logical hardware LED color. */
static const char* ledColorToCss(
  StatusLedColor color) {
  switch (color) {
    case StatusLedColor::RED:
      return "#ff0000";

    case StatusLedColor::ORANGE:
      return "#ff8000";

    case StatusLedColor::GREEN:
      return "#00ff00";

    case StatusLedColor::BLUE:
      return "#0000ff";

    case StatusLedColor::CYAN:
      return "#00ffff";

    case StatusLedColor::YELLOW:
      return "#ffff00";

    case StatusLedColor::MAGENTA:
      return "#ff00ff";

    case StatusLedColor::OFF:
    default:
      return "#666666";
  }
}

/** @brief Adds both currently rendered LED colors to a JSON document. */
static void addLedStatus(JsonDocument& doc) {
  StatusLedColor networkColor;
  StatusLedColor activityColor;
  getRenderedLedColors(
    networkColor,
    activityColor);

  JsonObject leds =
    doc["leds"].to<JsonObject>();
  leds["network"] =
    ledColorToCss(networkColor);
  leds["activity"] =
    ledColorToCss(activityColor);
}

static String getKnownArtNetName(
  const IPAddress& ip) {
  ArtNetSubscriberInfo subscriber;

  for (uint8_t i = 0;
       i < getArtNetSubscriberCount();
       i++) {
    if (!getArtNetSubscriber(i, subscriber)) {
      continue;
    }

    if (subscriber.ip == ip
        && subscriber.name[0] != '\0') {
      return String(subscriber.name);
    }
  }

  return ip.toString();
}

static void addArtNetSources(
  JsonDocument& doc) {
  JsonArray sources =
    doc["artNetSources"].to<JsonArray>();

  for (uint8_t i = 0;
       i < getArtNetSourceCount();
       i++) {
    ArtNetSourceInfo source;

    if (!getArtNetSource(i, source)) {
      continue;
    }

    JsonObject item =
      sources.add<JsonObject>();
    item["ip"] =
      source.ip.toString();
    item["name"] =
      getKnownArtNetName(source.ip);
    item["physical"] =
      source.physical;
    item["lastSeenAge"] =
      millis() - source.lastSeenMillis;
    item["winning"] =
      source.winning;
  }
}

/** @brief Sends the current LED state to one WebSocket client. */
static void sendLedStatus(uint8_t client) {
  JsonDocument doc;
  addLedStatus(doc);

  String json;
  serializeJson(doc, json);
  ws.sendTXT(client, json);
}

/** @brief Broadcasts a compact LED-only message after a color transition. */
static void broadcastLedStatusIfChanged() {
  StatusLedColor networkColor;
  StatusLedColor activityColor;
  getRenderedLedColors(
    networkColor,
    activityColor);

  if (ledStatusInitialized
      && networkColor == lastNetworkLedColor
      && activityColor == lastActivityLedColor) {
    return;
  }

  ledStatusInitialized = true;
  lastNetworkLedColor = networkColor;
  lastActivityLedColor = activityColor;

  JsonDocument doc;
  addLedStatus(doc);

  String json;
  serializeJson(doc, json);
  ws.broadcastTXT(json);
}

bool initWebSocket() {
  ws.begin();

  ws.onEvent(
    [](uint8_t client,
       WStype_t type,
       uint8_t* payload,
       size_t length) {
      switch (type) {
        case WStype_CONNECTED:
          {
            LOG_DEBUG_PRINT("WS Client connected: ");
            LOG_PRINTLN(LOG_LEVEL_DEBUG, client);

            sendLedStatus(client);

            break;
          }

        case WStype_DISCONNECTED:
          {
            LOG_DEBUG_PRINT("WS Client disconnected: ");
            LOG_PRINTLN(LOG_LEVEL_DEBUG, client);

            break;
          }

        default:
          break;
      }
    });

  LOG_INFO("WebSocket started");

  return true;
}

void broadcastStatus() {
  JsonDocument doc;
  JsonArray dmx =
    doc["dmx"]
      .to<JsonArray>();

  for (int i = 0; i < 32; i++) {
    dmx.add(
      getDmxChannel(i));
  }

  doc["uptime"] =
    millis();

  doc["artnetPackets"] =
    getArtDmxCounter();

  doc["artnetFPS"] =
    getArtNetFPS();

  doc["lastPacketAge"] =
    getLastArtNetPacketAge();

  doc["artnetActive"] =
    isArtNetActive();

  JsonObject artNetDiagnostics =
    doc["artNetDiagnostics"].to<JsonObject>();
  artNetDiagnostics["protocolDrops"] =
    getArtNetProtocolDropCount();
  artNetDiagnostics["wrongUniverseWarningActive"] =
    isArtNetWrongUniverseWarningActive();
  artNetDiagnostics["lastWrongUniverse"] =
    getArtNetLastWrongUniverse();

  doc["liveProtocol"] =
    config.liveProtocol;
  doc["sacnSourceName"] =
    config.sacnSourceName;
  doc["sacnPriority"] =
    config.sacnPriority;

  doc["sacnUniverse"] =
    getSacnUniverse();

  doc["sacnPackets"] =
    getSacnPacketCount();

  doc["sacnUdpPackets"] =
    getSacnUdpPacketCount();

  doc["sacnFPS"] =
    getSacnFPS();

  doc["lastSacnPacketAge"] =
    getLastSacnPacketAge();

  doc["sacnActive"] =
    isSacnActive();

  JsonObject sacnDiagnostics =
    doc["sacnDiagnostics"].to<JsonObject>();
  sacnDiagnostics["protocolDrops"] =
    getSacnProtocolDropCount();
  sacnDiagnostics["activeSources"] =
    getSacnActiveSourceCount();
  sacnDiagnostics["winningPriority"] =
    getSacnWinningPriority();
  sacnDiagnostics["sourceTimeouts"] =
    getSacnSourceTimeoutCount();

  doc["artSyncs"] =
    getArtSyncCounter();

  doc["lastSyncAge"] =
    getLastArtSyncAge();

  doc["artSyncActive"] =
    isArtSyncActive();

  doc["artSyncPending"] =
    isArtSyncPendingOutput();

  doc["direction"] =
    config.direction;

  doc["busGuardMode"] =
    config.busGuardMode;

  doc["buttonAction"] =
    config.buttonAction;

  doc["universe"] =
    getConfiguredUniverse();

  doc["mergeMode"] =
    config.mergeMode;

  doc["failsafeActive"] =
    config.liveProtocol == LIVE_PROTOCOL_SACN
      ? isSacnFailsafeActive()
      : isOutputFailsafeActive();

  doc["failsafeModeName"] =
    getFailsafeModeName();

  doc["artnetSubscribers"] =
    getArtNetSubscriberCount();

  addArtNetSources(doc);

  doc["dmxFrames"] =
    getDMXFrameCounter();

  doc["dmxFPS"] =
    getDMXFPS();

  doc["lastDMXFrameAge"] =
    getLastDMXFrameAge();

  doc["dmxActive"] =
    isDMXActive();

  doc["dmxTestOverride"] =
    isDmxTestOverrideActive();

  doc["dmxTestOverrideTimeoutEnabled"] =
    isDmxTestOverrideTimeoutEnabled();

  doc["dmxTestOverrideRemaining"] =
    getDmxTestOverrideRemaining();

  doc["artPolls"] =
    getArtPollCount();

  const uint32_t lastPollMillis =
    getLastArtPollMillis();

  doc["lastPollAge"] =
    lastPollMillis > 0
      ? millis() - lastPollMillis
      : 0;

  doc["wifiConnected"] =
    WiFi.isConnected();

  doc["wifiReconnectAttempts"] =
    getNetworkRetryCount();

  doc["wifiDisconnectedAge"] =
    getNetworkDisconnectedAge();

  doc["wifiRecoveryAP"] =
    isNetworkRecoveryAPActive();

  doc["squawking"] =
    isSquawking();

  const int rssi =
    WiFi.status() == WL_CONNECTED
      ? WiFi.RSSI()
      : -100;

  doc["rssi"] =
    rssi;

  doc["wifiQuality"] =
    constrain(
      2 * (rssi + 100),
      0,
      100);

  addLedStatus(doc);

  String json;

  serializeJson(
    doc,
    json);

  ws.broadcastTXT(json);
}

void updateWebSocket() {
  ws.loop();

  broadcastLedStatusIfChanged();

  uint32_t now =
    millis();

  if (now - lastBroadcast >= 500) {
    lastBroadcast = now;

    broadcastStatus();
  }
}
