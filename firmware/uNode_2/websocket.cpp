#include "websocket.h"

#include "config.h"
#include "artnet.h"
#include "sacn.h"
#include "dmx_frame.h"
#include "dmx.h"
#include "network.h"
#include "leds.h"
#include "status_json.h"

#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <ESP8266WiFi.h>

#undef LOG_MODULE
#define LOG_MODULE "WS"

static WebSocketsServer ws(81);

static uint32_t lastBroadcast = 0;
static bool ledStatusInitialized = false;
static StatusLedRgb lastNetworkLedColor =
  {0, 0, 0};
static StatusLedRgb lastActivityLedColor =
  {0, 0, 0};

/** @brief Formats one RGB value as a CSS hexadecimal color. */
static void ledColorToCss(
  const StatusLedRgb& color,
  char output[8]) {
  snprintf(
    output,
    8,
    "#%02x%02x%02x",
    color.red,
    color.green,
    color.blue);
}

/** @return True when both RGB values contain the same components. */
static bool ledColorsEqual(
  const StatusLedRgb& first,
  const StatusLedRgb& second) {
  return first.red == second.red
         && first.green == second.green
         && first.blue == second.blue;
}

/** @brief Adds both currently rendered LED colors to a JSON document. */
static void addLedStatus(JsonDocument& doc) {
  StatusLedRgb networkColor;
  StatusLedRgb activityColor;
  getRenderedLedColors(
    networkColor,
    activityColor);

  char networkCss[8];
  char activityCss[8];
  ledColorToCss(
    networkColor,
    networkCss);
  ledColorToCss(
    activityColor,
    activityCss);

  JsonObject leds =
    doc["leds"].to<JsonObject>();
  leds["network"] =
    networkCss;
  leds["activity"] =
    activityCss;
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
  StatusLedRgb networkColor;
  StatusLedRgb activityColor;
  getRenderedLedColors(
    networkColor,
    activityColor);

  if (ledStatusInitialized
      && ledColorsEqual(networkColor, lastNetworkLedColor)
      && ledColorsEqual(activityColor, lastActivityLedColor)) {
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

  JsonObject statusWarnings =
    doc["statusWarnings"].to<JsonObject>();
  statusWarnings["wrongUniverseWarningActive"] =
    isArtNetWrongUniverseWarningActive();
  statusWarnings["lastWrongUniverse"] =
    getArtNetLastWrongUniverse();
  statusWarnings["artNetProtocolDrops"] =
    getArtNetProtocolDropCount();
  statusWarnings["sacnProtocolDrops"] =
    getSacnProtocolDropCount();

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
    config.buttonShortAction;
  doc["buttonShortAction"] =
    config.buttonShortAction;
  doc["buttonLongAction"] =
    config.buttonLongAction;

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

  addArtNetSourcesToJson(doc);

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
  doc["ledIndicatorMode"] =
    getLedIndicatorMode();
  doc["ledMuted"] =
    areLEDsMuted();

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

  if (ws.connectedClients() == 0) {
    getRenderedLedColors(
      lastNetworkLedColor,
      lastActivityLedColor);
    ledStatusInitialized = true;
    return;
  }

  broadcastLedStatusIfChanged();

  uint32_t now =
    millis();

  if (now - lastBroadcast >= 500) {
    lastBroadcast = now;

    broadcastStatus();
  }
}
