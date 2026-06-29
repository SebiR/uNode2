#include "web.h"

#include "config.h"
#include "network.h"
#include "artnet.h"
#include "leds.h"
#include "dmx.h"
#include "dmx_frame.h"
#include "hardware.h"

#include <ESP8266WebServer.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <Updater.h>
#include <Hash.h>

#undef LOG_MODULE
#define LOG_MODULE "WEB"

ESP8266WebServer server(80);

static File configUploadFile;
static ConfigResult configUploadResult =
  ConfigResult::INVALID;
static String configUploadError =
  "No configuration file uploaded";
static int configUploadHttpStatus = 400;
static size_t configUploadDeclaredSize = 0;
static size_t configUploadWrittenSize = 0;
static bool restartScheduled = false;
static uint32_t restartAtMillis = 0;
static bool recoveryWebMode = false;
static bool recoveryFilesystemMounted = false;
static String updateUploadError =
  "No update uploaded";
static bool updateUploadSucceeded = false;
static size_t updateDeclaredSize = 0;
static size_t updateWrittenSize = 0;
static int updateCommand = U_FLASH;
static String authSessionToken;

static const char AUTH_HEADER[] = "X-uNode-Auth";
static const char AUTH_HASH_PREFIX[] = "uNode-admin:";
static const char WEB_ASSET_VERSION_PATH[] = "/version.json";
static const size_t MAX_AUTH_JSON_SIZE = 256;
static const size_t MAX_CONFIG_JSON_SIZE = 4096;
static const size_t MAX_CONFIG_UPLOAD_SIZE = 8192;
static const size_t MAX_BRIGHTNESS_JSON_SIZE = 64;
static const size_t MAX_DMX_JSON_SIZE = 3072;
static const uint32_t RTC_DIAGNOSTICS_OFFSET = 32;
static const uint32_t RTC_DIAGNOSTICS_MAGIC = 0x554E4F44UL;
static uint32_t minimumFreeHeap = UINT32_MAX;
static bool bootDiagnosticsInitialized = false;
static uint32_t bootCount = 0;

struct WebAssetVersionInfo {
  String version;
  bool present;
  bool matchesFirmware;
};

struct RtcDiagnostics {
  uint32_t magic;
  uint32_t bootCount;
  uint32_t checksum;
};

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

static const char RECOVERY_HTML[] PROGMEM = R"rawliteral(
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>uNode Recovery</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #e5e7eb; }
    header { padding: 24px; background: #1f2937; border-bottom: 1px solid #374151; }
    main { max-width: 760px; margin: 0 auto; padding: 20px; }
    .card { background: #1f2937; border: 1px solid #374151; border-radius: 12px; padding: 18px; margin: 16px 0; }
    button { background: #2563eb; color: white; border: 0; border-radius: 8px; padding: 10px 14px; margin-top: 10px; cursor: pointer; }
    button.warn { background: #d97706; }
    button.danger { background: #dc2626; }
    input { display: block; margin-top: 8px; }
    progress { width: 100%; height: 20px; margin-top: 12px; }
    code { background: #111827; padding: 2px 5px; border-radius: 4px; }
    .muted { color: #9ca3af; }
  </style>
</head>
<body>
  <header>
    <h1>uNode Recovery</h1>
    <p class="muted">Firmware-embedded service page. LittleFS is not required for this page.</p>
  </header>
  <main>
    <section class="card">
      <h2>Status</h2>
      <p id="status">Loading...</p>
      <p>Recovery address: <code>http://2.0.0.1</code></p>
    </section>

    <section class="card">
      <h2>Firmware Update</h2>
      <p>Upload the firmware <code>.bin</code> built for the explicit 4M1M flash layout.</p>
      <input id="firmwareFile" type="file" accept=".bin,.bin.gz">
      <button onclick="upload('firmwareFile','/api/update/firmware','Firmware update')">Upload Firmware</button>
    </section>

    <section class="card">
      <h2>LittleFS Update</h2>
      <p class="muted">This replaces the complete filesystem, including <code>/config.json</code>.</p>
      <input id="fsFile" type="file" accept=".bin,.img">
      <button class="warn" onclick="upload('fsFile','/api/update/fs','LittleFS update')">Upload LittleFS Image</button>
    </section>

    <section class="card">
      <h2>Configuration</h2>
      <button class="danger" onclick="factoryReset()">Factory Reset</button>
    </section>

    <section class="card">
      <h2>Wi-Fi Credentials</h2>
      <p class="muted" id="storedWifi">Stored Wi-Fi: unknown</p>
      <button class="warn" onclick="forgetWifi()">Forget Saved Wi-Fi Credentials</button>
    </section>

    <section class="card">
      <h2>Web Password</h2>
      <p class="muted">Leave empty and apply to disable web write protection.</p>
      <input id="adminPassword" type="password" placeholder="New password or empty">
      <button class="warn" onclick="setWebPassword()">Apply Password Setting</button>
    </section>

    <section class="card">
      <h2>Restart</h2>
      <button onclick="restart()">Restart Node</button>
      <progress id="progress" value="0" max="100" hidden></progress>
      <p id="message"></p>
    </section>
  </main>
  <script>
    async function refreshStatus() {
      try {
        const response = await fetch('/api/recovery/status');
        const data = await response.json();
        document.getElementById('status').textContent =
          `Firmware ${data.firmware}, flash layout ${data.flashLayout}, LittleFS image ${Math.round(data.littleFsImageSize / 1024)} kB`;
        document.getElementById('storedWifi').textContent =
          data.storedWifiConfigured
            ? `Stored Wi-Fi: ${data.storedWifiSSID}`
            : 'Stored Wi-Fi: none';
      } catch (error) {
        document.getElementById('status').textContent = 'Recovery status unavailable.';
      }
    }

    function setMessage(text) {
      document.getElementById('message').textContent = text;
    }

    function waitForRestart() {
      setMessage('Waiting for node to restart...');
      setTimeout(() => location.reload(), 12000);
    }

    function upload(inputId, url, label) {
      const file = document.getElementById(inputId).files[0];
      if (!file) {
        alert('Select a file first.');
        return;
      }

      if (url.endsWith('/fs') && !confirm('This replaces the complete LittleFS filesystem and may erase the current configuration. Continue?')) {
        return;
      }

      const progress = document.getElementById('progress');
      progress.hidden = false;
      progress.value = 0;
      setMessage(`${label} started...`);

      const form = new FormData();
      form.append('file', file);

      const request = new XMLHttpRequest();
      request.open('POST', `${url}?size=${file.size}`);
      request.upload.onprogress = event => {
        if (event.lengthComputable) {
          progress.value = Math.round((event.loaded / event.total) * 100);
        }
      };
      request.onload = () => {
        if (request.status >= 200 && request.status < 300) {
          progress.value = 100;
          setMessage(`${label} accepted. Rebooting...`);
          waitForRestart();
        } else {
          setMessage(`${label} failed: ${request.responseText}`);
        }
      };
      request.onerror = () => setMessage(`${label} failed: network error`);
      request.send(form);
    }

    async function restart() {
      await fetch('/api/restart', { method: 'POST' });
      waitForRestart();
    }

    async function factoryReset() {
      if (!confirm('Restore factory defaults?')) {
        return;
      }

      const response = await fetch('/api/factoryReset', { method: 'POST' });
      if (!response.ok) {
        setMessage('Factory reset failed: ' + await response.text());
        return;
      }

      setMessage('Factory reset completed. Rebooting...');
      waitForRestart();
    }

    async function forgetWifi() {
      if (!confirm('Forget the saved Wi-Fi SSID and password? The node will restart.')) {
        return;
      }

      const response = await fetch('/api/wifi/forget', { method: 'POST' });
      if (!response.ok) {
        setMessage('Clearing Wi-Fi credentials failed: ' + await response.text());
        return;
      }

      setMessage('Saved Wi-Fi credentials cleared. Rebooting...');
      waitForRestart();
    }

    async function setWebPassword() {
      const password = document.getElementById('adminPassword').value;
      const response = await fetch('/api/recovery/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });

      if (!response.ok) {
        setMessage('Password update failed: ' + await response.text());
        return;
      }

      document.getElementById('adminPassword').value = '';
      setMessage(password.length > 0
        ? 'Web password updated.'
        : 'Web password disabled.');
    }

    refreshStatus();
  </script>
</body>
</html>
)rawliteral";

/** @brief Schedules a restart after the current HTTP response can be sent. */
static void scheduleRestart(
  uint32_t delayMillis = 700) {
  LOG_INFO("Restart scheduled");

  restartScheduled = true;
  restartAtMillis =
    millis() + delayMillis;
}

/** @return True when a persisted configuration change needs a full reboot. */
static bool configChangeRequiresRestart(
  const Config& previous,
  const Config& current) {
  return previous.hostname != current.hostname
         || previous.wifiMode != current.wifiMode
         || previous.dhcp != current.dhcp
         || previous.ip != current.ip
         || previous.subnet != current.subnet
         || previous.gateway != current.gateway
         || previous.busGuardMode != current.busGuardMode
         || previous.adminPasswordHash != current.adminPasswordHash;
}

/** @brief Sends the JSON response used by the web UI after saving config. */
static void sendConfigSaveResponse(
  bool restartRequired,
  bool appliedLive,
  const String& message = "") {
  JsonDocument doc;
  doc["restartRequired"] = restartRequired;
  doc["appliedLive"] = appliedLive;

  if (message.length() > 0) {
    doc["message"] = message;
  }

  String json;
  serializeJson(
    doc,
    json);

  server.send(
    200,
    "application/json",
    json);
}

/** @return LittleFS web-asset version marker status. */
static WebAssetVersionInfo readWebAssetVersionInfo() {
  WebAssetVersionInfo info;
  info.version = "";
  info.present = false;
  info.matchesFirmware = false;

  File file =
    LittleFS.open(
      WEB_ASSET_VERSION_PATH,
      "r");

  if (!file) {
    return info;
  }

  JsonDocument doc;
  const DeserializationError error =
    deserializeJson(
      doc,
      file);

  file.close();

  if (error) {
    return info;
  }

  info.version =
    doc["version"] | "";
  info.present =
    info.version.length() > 0;
  info.matchesFirmware =
    info.present
    && info.version == FW_WEB_ASSET_VERSION;

  return info;
}

/** @return Simple checksum for the small RTC diagnostics block. */
static uint32_t checksumRtcDiagnostics(
  const RtcDiagnostics& data) {
  return data.magic
         ^ data.bootCount
         ^ 0xA5A55A5AUL;
}

/** @brief Initializes reset-surviving diagnostics stored in RTC user memory. */
static void initBootDiagnostics() {
  if (bootDiagnosticsInitialized) {
    return;
  }

  bootDiagnosticsInitialized = true;

  RtcDiagnostics data;

  const bool valid =
    ESP.rtcUserMemoryRead(
      RTC_DIAGNOSTICS_OFFSET,
      reinterpret_cast<uint32_t*>(&data),
      sizeof(data))
    && data.magic == RTC_DIAGNOSTICS_MAGIC
    && data.checksum == checksumRtcDiagnostics(data);

  if (!valid) {
    data.magic = RTC_DIAGNOSTICS_MAGIC;
    data.bootCount = 0;
  }

  data.bootCount++;
  data.checksum =
    checksumRtcDiagnostics(data);

  if (ESP.rtcUserMemoryWrite(
        RTC_DIAGNOSTICS_OFFSET,
        reinterpret_cast<uint32_t*>(&data),
        sizeof(data))) {
    bootCount = data.bootCount;
  } else {
    bootCount = 0;
  }
}

/** @return True when web write protection is configured. */
static bool isAuthEnabled() {
  return config.adminPasswordHash.length() > 0;
}

/** @return SHA1 hash used for optional web write protection. */
static String hashAdminPassword(
  const String& password) {
  return sha1(
    String(AUTH_HASH_PREFIX) + password);
}

/** @return New volatile session token for the current boot. */
static String createAuthToken() {
  String token;
  token.reserve(32);

  for (uint8_t i = 0; i < 4; i++) {
    const uint32_t value =
      ((uint32_t)random(65536) << 16)
      | (uint32_t)random(65536);

    char part[9];
    snprintf(
      part,
      sizeof(part),
      "%08lx",
      (unsigned long)value);
    token += part;
  }

  return token;
}

/** @return True when no password is configured or the request has a valid token. */
static bool isAuthorizedRequest() {
  if (!isAuthEnabled()) {
    return true;
  }

  const String token =
    server.header(AUTH_HEADER);

  return authSessionToken.length() > 0
         && token == authSessionToken;
}

/** @brief Sends a 403 response when a mutating endpoint is locked. */
static bool requireAuth() {
  if (isAuthorizedRequest()) {
    return true;
  }

  server.send(
    403,
    "text/plain",
    "Login required");

  return false;
}

/** @brief Rejects oversized JSON/plain request bodies before parsing. */
static bool requirePlainBodyLimit(
  size_t maxBytes,
  const char* label) {
  const size_t bodySize =
    server.arg("plain").length();

  if (bodySize <= maxBytes) {
    return true;
  }

  LOG_WARN_PRINT(label);
  LOG_PRINT(LOG_LEVEL_WARN, " body too large: ");
  LOG_PRINTLN(LOG_LEVEL_WARN, bodySize);

  server.send(
    413,
    "text/plain",
    String(label) + " request body is too large");

  return false;
}

/** @brief Sends the current auth state to the browser. */
static void handleAuthStatus() {
  JsonDocument doc;
  doc["enabled"] =
    isAuthEnabled();
  doc["authenticated"] =
    isAuthorizedRequest();

  String json;
  serializeJson(doc, json);

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Authenticates one browser and returns a volatile session token. */
static void handleAuthLogin() {
  if (!isAuthEnabled()) {
    JsonDocument doc;
    doc["token"] = "";
    doc["authenticated"] = true;

    String json;
    serializeJson(doc, json);

    server.send(
      200,
      "application/json",
      json);
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_AUTH_JSON_SIZE,
        "Auth login")) {
    return;
  }

  JsonDocument doc;
  if (deserializeJson(
        doc,
        server.arg("plain"))) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");
    return;
  }

  const String password =
    doc["password"] | "";

  if (hashAdminPassword(password)
      != config.adminPasswordHash) {
    server.send(
      403,
      "text/plain",
      "Invalid password");
    return;
  }

  authSessionToken =
    createAuthToken();

  JsonDocument response;
  response["token"] =
    authSessionToken;
  response["authenticated"] =
    true;

  String json;
  serializeJson(response, json);

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Clears the volatile browser session token. */
static void handleAuthLogout() {
  if (server.header(AUTH_HEADER) == authSessionToken) {
    authSessionToken = "";
  }

  server.send(
    200,
    "text/plain",
    "OK");
}

/** @brief Stores or clears the optional web admin password. */
static void handleAuthPassword() {
  if (!requireAuth()) {
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_AUTH_JSON_SIZE,
        "Auth password")) {
    return;
  }

  JsonDocument doc;
  if (deserializeJson(
        doc,
        server.arg("plain"))) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");
    return;
  }

  const String password =
    doc["password"] | "";

  String error;
  const ConfigResult result =
    updateAdminPasswordHash(
      password.length() > 0
        ? hashAdminPassword(password)
        : "",
      error);

  if (result != ConfigResult::OK) {
    server.send(
      result == ConfigResult::INVALID ? 400 : 500,
      "text/plain",
      error);
    return;
  }

  if (password.length() == 0) {
    authSessionToken = "";
  } else if (authSessionToken.length() == 0) {
    authSessionToken =
      createAuthToken();
  }

  JsonDocument response;
  response["enabled"] =
    isAuthEnabled();
  response["token"] =
    authSessionToken;

  String json;
  serializeJson(response, json);

  server.send(
    200,
    "application/json",
    json);
}

/** @return Maximum firmware image size accepted by the OTA updater. */
static size_t getMaxFirmwareUpdateSize() {
  return (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
}

/** @return File size declared by the browser in the upload query string. */
static size_t getDeclaredUploadSize() {
  if (!server.hasArg("size")) {
    return 0;
  }

  const String value =
    server.arg("size");

  char* end = nullptr;
  const unsigned long parsed =
    strtoul(
      value.c_str(),
      &end,
      10);

  if (!end || *end != '\0') {
    return 0;
  }

  return parsed;
}

/** @brief Starts one firmware or filesystem update transaction. */
static bool beginUpdateUpload(
  int command) {
  updateUploadError = "";
  updateUploadSucceeded = false;
  updateDeclaredSize =
    getDeclaredUploadSize();
  updateWrittenSize = 0;
  updateCommand = command;

  LOG_INFO_PRINT(
    command == U_FS
      ? "LittleFS update upload started, bytes: "
      : "Firmware update upload started, bytes: ");
  LOG_PRINTLN(
    LOG_LEVEL_INFO,
    updateDeclaredSize);

  if (updateDeclaredSize == 0) {
    updateUploadError =
      "Upload size is missing or invalid";
    LOG_WARN(updateUploadError);
    return false;
  }

  if (command == U_FLASH
      && updateDeclaredSize > getMaxFirmwareUpdateSize()) {
    updateUploadError =
      "Firmware image is too large for the OTA slot";
    LOG_WARN(updateUploadError);
    return false;
  }

  if (command == U_FS
      && updateDeclaredSize != FW_LITTLEFS_IMAGE_SIZE) {
    updateUploadError =
      "LittleFS image size does not match the configured 4M1M filesystem";
    LOG_WARN(updateUploadError);
    return false;
  }

  if (command == U_FS) {
    LittleFS.end();
    recoveryFilesystemMounted = false;
  }

  if (!Update.begin(
        updateDeclaredSize,
        command)) {
    updateUploadError =
      Update.getErrorString();
    LOG_ERROR_PRINT("Update.begin failed: ");
    LOG_PRINTLN(LOG_LEVEL_ERROR, updateUploadError);
    return false;
  }

  return true;
}

/** @brief Handles streaming upload data for firmware or filesystem OTA. */
static void handleUpdateUpload(
  int command) {
  if (!recoveryWebMode
      && !isAuthorizedRequest()) {
    return;
  }

  HTTPUpload& upload =
    server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    beginUpdateUpload(command);
  } else if (
    upload.status == UPLOAD_FILE_WRITE) {
    if (updateUploadError.length() > 0) {
      return;
    }

    if (updateWrittenSize + upload.currentSize
        > updateDeclaredSize) {
      updateUploadError =
        "Upload exceeds declared size";
      LOG_WARN(updateUploadError);
      return;
    }

    const size_t written =
      Update.write(
        upload.buf,
        upload.currentSize);

    updateWrittenSize += written;

    if (written != upload.currentSize) {
      updateUploadError =
        Update.getErrorString();
      LOG_ERROR_PRINT("Update.write failed: ");
      LOG_PRINTLN(LOG_LEVEL_ERROR, updateUploadError);
    }
  } else if (
    upload.status == UPLOAD_FILE_END) {
    if (updateUploadError.length() == 0
        && updateWrittenSize != updateDeclaredSize) {
      updateUploadError =
        "Upload size mismatch";
    }

    if (updateUploadError.length() == 0) {
      if (!Update.end(false)) {
        updateUploadError =
          Update.getErrorString();
        LOG_ERROR_PRINT("Update.end failed: ");
        LOG_PRINTLN(LOG_LEVEL_ERROR, updateUploadError);
      } else {
        updateUploadSucceeded = true;
        LOG_INFO("Update upload completed");
      }
    } else if (Update.isRunning()) {
      Update.end(false);
    }
  } else if (
    upload.status == UPLOAD_FILE_ABORTED) {
    if (Update.isRunning()) {
      Update.end(false);
    }

    updateUploadError =
      "Upload aborted";
    LOG_WARN(updateUploadError);
  }
}

/** @brief Sends the final response after an OTA upload transaction. */
static void handleUpdateComplete(
  const char* successMessage) {
  if (!recoveryWebMode
      && !requireAuth()) {
    return;
  }

  if (!updateUploadSucceeded) {
    LOG_ERROR_PRINT("Update failed: ");
    LOG_PRINTLN(
      LOG_LEVEL_ERROR,
      updateUploadError.length() > 0
        ? updateUploadError
        : "Update failed");

    server.send(
      500,
      "text/plain",
      updateUploadError.length() > 0
        ? updateUploadError
        : "Update failed");

    return;
  }

  server.send(
    200,
    "text/plain",
    successMessage);

  scheduleRestart();
}

/** @return HTTP content type inferred from a file name extension. */
static String getContentType(const String& filename) {
  if (filename.endsWith(".html")) return "text/html";
  if (filename.endsWith(".css")) return "text/css";
  if (filename.endsWith(".js")) return "application/javascript";
  if (filename.endsWith(".png")) return "image/png";
  if (filename.endsWith(".jpg")) return "image/jpeg";
  if (filename.endsWith(".ico")) return "image/x-icon";
  if (filename.endsWith(".svg")) return "image/svg+xml";
  if (filename.endsWith(".json")) return "application/json";
  if (filename.endsWith(".webmanifest")) return "application/manifest+json";

  return "text/plain";
}

/** @brief Prevents stale LittleFS web assets after firmware or filesystem updates. */
static void sendStaticCacheHeaders() {
  server.sendHeader(
    "Cache-Control",
    "no-store, no-cache, must-revalidate, max-age=0");
  server.sendHeader(
    "Pragma",
    "no-cache");
  server.sendHeader(
    "Expires",
    "0");
}

/** @brief Streams one LittleFS asset to the current HTTP client. */
static bool handleFileRead(String path) {
  if (path.endsWith("/")) {
    path += "index.html";
  }

  if (!LittleFS.exists(path)) {
    return false;
  }

  File file = LittleFS.open(path, "r");

  sendStaticCacheHeaders();

  server.streamFile(
    file,
    getContentType(path));

  file.close();

  return true;
}

/** @brief Responds with the complete runtime status JSON document. */
static void handleStatus() {
  JsonDocument doc;
  initBootDiagnostics();

  FSInfo fsInfo;
  LittleFS.info(fsInfo);

  const uint32_t freeHeap =
    ESP.getFreeHeap();

  if (freeHeap < minimumFreeHeap) {
    minimumFreeHeap = freeHeap;
  }

  IPAddress ip;
  IPAddress subnet;
  IPAddress gateway;

  if (WiFi.status() != WL_CONNECTED) {
    ip = WiFi.softAPIP();

    subnet = IPAddress(
      255, 255, 255, 0);

    gateway = WiFi.softAPIP();
  } else {
    ip = WiFi.localIP();

    subnet = WiFi.subnetMask();

    gateway = WiFi.gatewayIP();
  }

  doc["name"] = config.shortName;

  doc["firmware"] = FW_VERSION;
  doc["buildDate"] = FW_BUILD_DATE;
  doc["buildTime"] = FW_BUILD_TIME;
  doc["flashLayout"] = FW_FLASH_LAYOUT;
  doc["configSchemaVersion"] = CONFIG_SCHEMA_VERSION;
  doc["littleFsImageSize"] = FW_LITTLEFS_IMAGE_SIZE;

  const WebAssetVersionInfo webAssets =
    readWebAssetVersionInfo();
  doc["webAssetExpectedVersion"] =
    FW_WEB_ASSET_VERSION;
  doc["webAssetVersion"] =
    webAssets.present
      ? webAssets.version
      : "";
  doc["webAssetVersionPresent"] =
    webAssets.present;
  doc["webAssetVersionMatch"] =
    webAssets.matchesFirmware;

  doc["recoveryMode"] = recoveryWebMode;

  doc["hostname"] = config.hostname;
  doc["ip"] = getIPAddress();

  doc["wifiIp"] =
    ip.toString();

  doc["wifiSubnet"] =
    subnet.toString();

  doc["wifiGateway"] =
    gateway.toString();
  doc["mac"] =
    WiFi.macAddress();

  String chipId =
    String(
      ESP.getChipId(),
      HEX);

  chipId.toUpperCase();

  doc["chipId"] =
    chipId;

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

  doc["wifiConnected"] =
    WiFi.status() == WL_CONNECTED;

  doc["wifiReconnectAttempts"] =
    getNetworkRetryCount();

  doc["wifiDisconnectedAge"] =
    getNetworkDisconnectedAge();

  doc["wifiRecoveryAP"] =
    isNetworkRecoveryAPActive();

  doc["storedWifiSSID"] =
    getStoredWifiSSID();

  doc["storedWifiConfigured"] =
    hasStoredWifiCredentials();

  doc["softAPActive"] =
    isSoftAPInterfaceActive();

  doc["softAPStations"] =
    getSoftAPStationCount();

  doc["softAPIP"] =
    getSoftAPIPAddress();

  doc["uptime"] = millis();

  doc["freeHeap"] =
    freeHeap;

  doc["maxFreeBlock"] =
    ESP.getMaxFreeBlockSize();

  doc["heapFragmentation"] =
    ESP.getHeapFragmentation();

  doc["minimumFreeHeap"] =
    minimumFreeHeap;

  doc["resetReason"] =
    ESP.getResetReason();

  doc["resetInfo"] =
    ESP.getResetInfo();

  doc["bootCount"] =
    bootCount;

  doc["flashSize"] =
    ESP.getFlashChipSize();

  doc["sketchSize"] =
    ESP.getSketchSize();

  doc["freeSketch"] =
    ESP.getFreeSketchSpace();

  doc["fsTotal"] =
    fsInfo.totalBytes;

  doc["fsUsed"] =
    fsInfo.usedBytes;

  doc["artnetPackets"] =
    getArtDmxCounter();

  doc["artnetFPS"] =
    getArtNetFPS();

  doc["lastPacketAge"] =
    getLastArtNetPacketAge();

  doc["artSyncs"] =
    getArtSyncCounter();

  doc["lastSyncAge"] =
    getLastArtSyncAge();

  doc["artSyncActive"] =
    isArtSyncActive();

  doc["artSyncPending"] =
    isArtSyncPendingOutput();

  JsonObject artNetDiagnostics =
    doc["artNetDiagnostics"].to<JsonObject>();
  artNetDiagnostics["oversizedPackets"] =
    getArtNetOversizedPacketCount();
  artNetDiagnostics["shortPackets"] =
    getArtNetShortPacketCount();
  artNetDiagnostics["invalidIdPackets"] =
    getArtNetInvalidIdPacketCount();
  artNetDiagnostics["unsupportedProtocolPackets"] =
    getArtNetUnsupportedProtocolCount();
  artNetDiagnostics["malformedPackets"] =
    getArtNetMalformedPacketCount();
  artNetDiagnostics["unsupportedOpcodes"] =
    getArtNetUnsupportedOpcodeCount();
  artNetDiagnostics["wrongUniversePackets"] =
    getArtNetWrongUniverseCount();
  artNetDiagnostics["lastWrongUniverse"] =
    getArtNetLastWrongUniverse();
  artNetDiagnostics["lastWrongUniverseAge"] =
    getArtNetLastWrongUniverseAge();
  artNetDiagnostics["wrongUniverseWarningActive"] =
    isArtNetWrongUniverseWarningActive();
  artNetDiagnostics["directionDrops"] =
    getArtNetDirectionDropCount();
  artNetDiagnostics["sequenceDrops"] =
    getArtNetSequenceDropCount();
  artNetDiagnostics["mergeLockDrops"] =
    getArtNetMergeLockDropCount();
  artNetDiagnostics["mergeThirdSourceDrops"] =
    getArtNetMergeThirdSourceDropCount();
  artNetDiagnostics["syncTimeouts"] =
    getArtNetSyncTimeoutCount();

  doc["artPolls"] =
    getArtPollCount();

  if (getLastArtPollMillis() > 0) {
    doc["lastPollAge"] =
      millis() - getLastArtPollMillis();
  } else {
    doc["lastPollAge"] = 0;
  }

  doc["artnetActive"] =
    isArtNetActive();

  doc["failsafeMode"] =
    config.failsafeMode;

  doc["mergeMode"] =
    config.mergeMode;

  doc["failsafeModeName"] =
    getFailsafeModeName();

  doc["failsafeActive"] =
    isOutputFailsafeActive();

  doc["legacyArtPollReply"] =
    config.legacyArtPollReply;

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

  doc["squawking"] =
    isSquawking();

  IPAddress broadcast =
    getArtNetBroadcast();

  doc["universe"] =
    getConfiguredUniverse();

  doc["direction"] =
    config.direction;

  doc["rs485SplitControlSupported"] =
    isRs485SplitControlSupported();

  doc["rs485DriverEnabled"] =
    isRs485DriverEnabled();

  doc["rs485ReceiverEnabled"] =
    isRs485ReceiverEnabled();

  doc["terminationControlSupported"] =
    isTerminationControlSupported();

  doc["terminationMode"] =
    config.terminationMode;

  doc["busGuardMode"] =
    config.busGuardMode;

  doc["terminationEnabled"] =
    isTerminationEnabled();

#if USE_WS2812
  doc["ledHardware"] = "WS2812";
  doc["ledBrightnessSupported"] = true;
#else
  doc["ledHardware"] = "Legacy";
  doc["ledBrightnessSupported"] =
    USE_LED_PWM != 0;
#endif

  LOG_TRACE_PRINT("Status IP: ");
  LOG_PRINTLN(LOG_LEVEL_TRACE, ip.toString());

  LOG_TRACE_PRINT("Status subnet: ");
  LOG_PRINTLN(LOG_LEVEL_TRACE, subnet.toString());

  LOG_TRACE_PRINT("Status broadcast: ");
  LOG_PRINTLN(LOG_LEVEL_TRACE, broadcast.toString());

  doc["broadcastIP"] =
    broadcast.toString();

  doc["artnetSubscribers"] =
    getArtNetSubscriberCount();

  addArtNetSources(doc);

  doc["subnet"] = WiFi.subnetMask().toString();

  String json;

  serializeJson(
    doc,
    json);

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Responds with the active configuration as JSON. */
static void handleConfig() {
  String json;

  if (!serializeConfig(json)) {
    server.send(
      500,
      "text/plain",
      "Failed to serialize configuration");

    return;
  }

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Validates and stores a configuration supplied in the request body. */
static void handleSaveConfig() {
  if (!recoveryWebMode
      && !requireAuth()) {
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_CONFIG_JSON_SIZE,
        "Config save")) {
    return;
  }

  const Config previousConfig =
    config;

  String error;
  const ConfigResult result =
    updateConfigFromJson(
      server.arg("plain"),
      error);

  if (result != ConfigResult::OK) {
    server.send(
      result == ConfigResult::INVALID ? 400 : 500,
      "text/plain",
      error);

    return;
  }

  bool restartRequired =
    configChangeRequiresRestart(
      previousConfig,
      config);
  bool appliedLive = false;
  String message;

  if (!restartRequired) {
    setLEDBrightness(
      config.ledBrightness);

    if (applyArtNetRuntimeConfig(
          previousConfig,
          message)) {
      appliedLive = true;
    } else {
      restartRequired = true;
    }
  }

  sendConfigSaveResponse(
    restartRequired,
    appliedLive,
    message);
}

/** @brief Acknowledges the request and restarts the controller. */
static void handleRestart() {
  if (!recoveryWebMode
      && !requireAuth()) {
    return;
  }

  server.send(
    200,
    "text/plain",
    "Restarting");

  scheduleRestart();
}

/** @brief Erases stored station credentials and restarts into configured mode. */
static void handleForgetWifiCredentials() {
  if (!recoveryWebMode
      && !requireAuth()) {
    return;
  }

  const bool cleared =
    forgetStoredWifiCredentials();

  if (!cleared) {
    server.send(
      500,
      "text/plain",
      "Failed to clear saved Wi-Fi credentials");

    return;
  }

  JsonDocument doc;
  doc["restartRequired"] = true;
  doc["message"] =
    "Saved Wi-Fi credentials cleared. Restarting.";
  doc["storedWifiConfigured"] = false;

  String json;
  serializeJson(
    doc,
    json);

  server.send(
    200,
    "application/json",
    json);

  scheduleRestart();
}

/** @brief Toggles local Art-Net Locate indication. */
static void handleDetectNode() {
  if (!requireAuth()) {
    return;
  }

  toggleArtNetLocate();

  server.send(
    200,
    "text/plain",
    "OK");
}

/** @brief Serves static assets or returns an HTTP 404 response. */
static void handleNotFound() {
  if (handleFileRead(server.uri())) {
    return;
  }

  server.send(
    404,
    "text/plain",
    "404 Not Found");
}

/** @brief Applies a temporary LED brightness value from JSON. */
static void handleBrightness() {
  if (!requireAuth()) {
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_BRIGHTNESS_JSON_SIZE,
        "Brightness")) {
    return;
  }

  JsonDocument doc;

  DeserializationError error =
    deserializeJson(
      doc,
      server.arg("plain"));

  if (error) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");

    return;
  }

  uint8_t brightness =
    constrain(
      doc["brightness"] | 50,
      0,
      100);

  setLEDBrightness(
    brightness);

  server.send(
    200,
    "text/plain",
    "OK");
}

/** @brief Restores persisted defaults and restarts the controller. */
static void handleFactoryReset() {
  if (!recoveryWebMode
      && !requireAuth()) {
    return;
  }

  LOG_WARN(
    "Factory reset requested");

  if (recoveryWebMode
      && !recoveryFilesystemMounted) {
    server.send(
      500,
      "text/plain",
      "LittleFS is not mounted. Upload a LittleFS image first.");

    return;
  }

  String error;

  if (resetConfig(error) != ConfigResult::OK) {
    server.send(
      500,
      "text/plain",
      error);

    return;
  }

  server.send(
    200,
    "text/plain",
    "Factory reset completed");

  scheduleRestart();
}

/** @brief Streams the firmware-embedded recovery page. */
static void handleRecoveryPage() {
  server.send_P(
    200,
    "text/html",
    RECOVERY_HTML);
}

/** @brief Responds with small diagnostics needed by the recovery page. */
static void handleRecoveryStatus() {
  JsonDocument doc;

  doc["firmware"] = FW_VERSION;
  doc["buildDate"] = FW_BUILD_DATE;
  doc["buildTime"] = FW_BUILD_TIME;
  doc["flashLayout"] = FW_FLASH_LAYOUT;
  doc["littleFsImageSize"] = FW_LITTLEFS_IMAGE_SIZE;
  doc["chipId"] = getChipIdString();
  doc["fsMounted"] = recoveryFilesystemMounted;
  doc["freeSketch"] = ESP.getFreeSketchSpace();
  doc["storedWifiSSID"] = getStoredWifiSSID();
  doc["storedWifiConfigured"] = hasStoredWifiCredentials();

  String json;
  serializeJson(doc, json);

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Sets or clears the web password from recovery mode. */
static void handleRecoveryAuthPassword() {
  if (!recoveryFilesystemMounted) {
    server.send(
      500,
      "text/plain",
      "LittleFS is not mounted. Upload a LittleFS image first.");
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_AUTH_JSON_SIZE,
        "Recovery password")) {
    return;
  }

  JsonDocument doc;
  if (deserializeJson(
        doc,
        server.arg("plain"))) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");
    return;
  }

  const String password =
    doc["password"] | "";

  loadConfig();

  String error;
  const ConfigResult result =
    updateAdminPasswordHash(
      password.length() > 0
        ? hashAdminPassword(password)
        : "",
      error);

  if (result != ConfigResult::OK) {
    server.send(
      result == ConfigResult::INVALID ? 400 : 500,
      "text/plain",
      error);
    return;
  }

  authSessionToken = "";

  server.send(
    200,
    "text/plain",
    "OK");
}

/** @brief Receives one firmware binary through multipart upload. */
static void handleFirmwareUpdateUpload() {
  handleUpdateUpload(
    U_FLASH);
}

/** @brief Receives one complete LittleFS image through multipart upload. */
static void handleFilesystemUpdateUpload() {
  handleUpdateUpload(
    U_FS);
}

/** @brief Finalizes the firmware update request. */
static void handleFirmwareUpdateComplete() {
  handleUpdateComplete(
    "Firmware update accepted. Restarting.");
}

/** @brief Finalizes the filesystem update request. */
static void handleFilesystemUpdateComplete() {
  handleUpdateComplete(
    "LittleFS update accepted. Restarting.");
}

/** @brief Streams the persisted configuration as an attachment. */
static void handleDownloadConfig() {
  if (!requireAuth()) {
    return;
  }

  if (!LittleFS.exists("/config.json")) {
    server.send(
      404,
      "text/plain",
      "Config not found");

    return;
  }

  File file =
    LittleFS.open(
      "/config.json",
      "r");

  server.sendHeader(
    "Content-Disposition",
    "attachment; filename=config.json");

  server.streamFile(
    file,
    "application/json");

  file.close();
}

/** @brief Receives, validates, and atomically imports a config upload. */
static void handleUploadConfig() {
  if (!isAuthorizedRequest()) {
    return;
  }

  HTTPUpload& upload =
    server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    if (configUploadFile) {
      configUploadFile.close();
    }

    LittleFS.remove("/config.upload");

    configUploadResult = ConfigResult::INVALID;
    configUploadError = "";
    configUploadHttpStatus = 400;
    configUploadDeclaredSize =
      getDeclaredUploadSize();
    configUploadWrittenSize = 0;

    if (configUploadDeclaredSize > MAX_CONFIG_UPLOAD_SIZE) {
      configUploadError =
        "Configuration upload is too large";
      configUploadHttpStatus = 413;
      return;
    }

    configUploadFile =
      LittleFS.open(
        "/config.upload",
        "w");

    if (!configUploadFile) {
      configUploadResult =
        ConfigResult::STORAGE_ERROR;
      configUploadError =
        "Failed to create temporary upload file";
      configUploadHttpStatus = 500;
    }
  } else if (
    upload.status == UPLOAD_FILE_WRITE) {
    if (configUploadError.length() == 0
        && configUploadWrittenSize + upload.currentSize
            > MAX_CONFIG_UPLOAD_SIZE) {
      configUploadResult =
        ConfigResult::INVALID;
      configUploadError =
        "Configuration upload is too large";
      configUploadHttpStatus = 413;

      if (configUploadFile) {
        configUploadFile.close();
      }

      LittleFS.remove("/config.upload");
      return;
    }

    if (configUploadFile
        && configUploadError.length() == 0) {
      const size_t written =
        configUploadFile.write(
          upload.buf,
          upload.currentSize);

      configUploadWrittenSize += written;

      if (written != upload.currentSize) {
        configUploadResult =
          ConfigResult::STORAGE_ERROR;
        configUploadError =
          "Failed to write uploaded configuration";
        configUploadHttpStatus = 500;
      }
    }
  } else if (
    upload.status == UPLOAD_FILE_END) {
    if (configUploadFile) {
      configUploadFile.close();
    }

    if (configUploadError.length() == 0) {
      configUploadResult =
        importConfigFile(
          "/config.upload",
          configUploadError);
      configUploadHttpStatus =
        configUploadResult == ConfigResult::STORAGE_ERROR
          ? 500
          : 400;
    }

    LittleFS.remove("/config.upload");
  } else if (
    upload.status == UPLOAD_FILE_ABORTED) {
    if (configUploadFile) {
      configUploadFile.close();
    }

    LittleFS.remove("/config.upload");
    configUploadResult = ConfigResult::INVALID;
    configUploadError = "Configuration upload aborted";
  }
}

/** @brief Triggers an immediate ArtPoll for subscriber discovery. */
static void handlePollArtNetSubscribers() {
  if (!requireAuth()) {
    return;
  }

  startArtNetDiscovery();

  server.send(
    202,
    "text/plain",
    "Art-Net subscriber poll started");
}

/** @brief Responds with subscribers matching the configured Port-Address. */
static void handleArtNetSubscribers() {
  JsonDocument doc;

  doc["polling"] =
    isArtNetDiscoveryActive();

  doc["universe"] =
    getConfiguredUniverse();

  const uint32_t lastPoll =
    getLastSubscriberPollMillis();
  doc["lastPollAge"] =
    lastPoll > 0 ? millis() - lastPoll : 0;

  JsonArray items =
    doc["subscribers"].to<JsonArray>();

  for (uint8_t i = 0;
       i < getArtNetSubscriberCount();
       i++) {
    ArtNetSubscriberInfo subscriber;

    if (!getArtNetSubscriber(i, subscriber)) {
      continue;
    }

    JsonObject item =
      items.add<JsonObject>();

    item["name"] = subscriber.name;
    item["ip"] = subscriber.ip.toString();
    item["bindIndex"] = subscriber.bindIndex;
    item["inputPortMask"] = subscriber.inputPortMask;
    item["outputPortMask"] = subscriber.outputPortMask;
    item["lastSeenAge"] =
      millis() - subscriber.lastSeenMillis;
  }

  String json;
  serializeJson(doc, json);

  server.send(
    200,
    "application/json",
    json);
}

/** @brief Applies one or multiple temporary test-channel values supplied as JSON. */
static void handleDmxValue() {
  if (!requireAuth()) {
    return;
  }

  if (!requirePlainBodyLimit(
        MAX_DMX_JSON_SIZE,
        "DMX test")) {
    return;
  }

  JsonDocument doc;

  if (deserializeJson(
        doc,
        server.arg("plain"))) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");

    return;
  }

  bool changed = false;
  bool touched = false;

  if (doc["values"].is<JsonArrayConst>()) {
    int startChannel =
      doc["startChannel"] | 1;

    JsonArrayConst values =
      doc["values"].as<JsonArrayConst>();

    if (startChannel < 1
        || startChannel + (int)values.size() - 1 > 512) {
      server.send(
        400,
        "text/plain",
        "Invalid channel range");

      return;
    }

    uint16_t index =
      startChannel - 1;

    for (JsonVariantConst item : values) {
      const uint8_t value =
        constrain(
          item.as<int>(),
          0,
          255);

      changed |= setDmxTestChannel(
        index,
        value);
      touched = true;
      index++;
    }
  } else {
    int channel =
      doc["channel"] | 1;

    int value =
      doc["value"] | 0;

    if (channel < 1 || channel > 512) {
      server.send(
        400,
        "text/plain",
        "Invalid channel");

      return;
    }

    value =
      constrain(
        value,
        0,
        255);

    LOG_TRACE_PRINT("DMX test CH=");
    LOG_PRINT(LOG_LEVEL_TRACE, channel);

    LOG_TRACE_PRINT(" VAL=");
    LOG_PRINTLN(LOG_LEVEL_TRACE, value);

    changed =
      setDmxTestChannel(
        channel - 1,
        value);
    touched = true;
  }

  if (touched
      && config.direction == DMX_TO_ARTNET) {
    sendArtNetFrame();
  }

  server.send(
    200,
    "application/json",
    "{\"ok\":true}");
}

/** @brief Releases the temporary local DMX test override. */
static void handleReleaseDmxOverride() {
  if (!requireAuth()) {
    return;
  }

  const bool changed =
    releaseDmxTestOverride();

  if (changed
      && config.direction == DMX_TO_ARTNET) {
    sendArtNetFrame();
  }

  server.send(
    200,
    "application/json",
    "{\"ok\":true}");
}

/** @brief Updates the non-persistent DMX test override timeout mode. */
static void handleDmxOverrideTimeout() {
  if (!requireAuth()) {
    return;
  }

  if (!requirePlainBodyLimit(
        128,
        "DMX override timeout")) {
    return;
  }

  JsonDocument doc;

  if (deserializeJson(
        doc,
        server.arg("plain"))) {
    server.send(
      400,
      "text/plain",
      "Invalid JSON");

    return;
  }

  setDmxTestOverrideTimeoutEnabled(
    doc["enabled"] | true);

  server.send(
    200,
    "application/json",
    "{\"ok\":true}");
}

/** @brief Records the current output frame as persistent failsafe scene. */
static void handleRecordFailsafeScene() {
  if (!requireAuth()) {
    return;
  }

  String error;

  if (!recordFailsafeScene(error)) {
    server.send(
      500,
      "text/plain",
      error);

    return;
  }

  server.send(
    200,
    "text/plain",
    "Failsafe scene recorded");
}

bool initWeb() {
  LOG_SECTION("Web Init");

  server.collectHeaders(
    AUTH_HEADER);

  server.on(
    "/api/status",
    HTTP_GET,
    handleStatus);

  server.on(
    "/api/auth/status",
    HTTP_GET,
    handleAuthStatus);

  server.on(
    "/api/auth/login",
    HTTP_POST,
    handleAuthLogin);

  server.on(
    "/api/auth/logout",
    HTTP_POST,
    handleAuthLogout);

  server.on(
    "/api/auth/password",
    HTTP_POST,
    handleAuthPassword);

  server.on(
    "/",
    HTTP_GET,
    []() {
      if (handleFileRead("/index.html")) {
        return;
      }

      server.send(
        500,
        "text/plain",
        "Web interface asset /index.html is missing. Upload the LittleFS image or reboot into recovery mode.");
    });

  server.on(
    "/api/config",
    HTTP_GET,
    handleConfig);

  server.on(
    "/api/config",
    HTTP_POST,
    handleSaveConfig);

  server.on(
    "/api/restart",
    HTTP_POST,
    handleRestart);

  server.on(
    "/api/wifi/forget",
    HTTP_POST,
    handleForgetWifiCredentials);

  server.on(
    "/api/detect",
    HTTP_POST,
    handleDetectNode);

  server.on(
    "/api/brightness",
    HTTP_POST,
    handleBrightness);

  server.on(
    "/api/config/upload",
    HTTP_POST,
    []() {
      if (!requireAuth()) {
        return;
      }

      const int status =
        configUploadResult == ConfigResult::OK
          ? 200
          : configUploadHttpStatus;

      server.send(
        status,
        "text/plain",
        configUploadResult == ConfigResult::OK
          ? "Upload complete"
          : configUploadError);
    },
    handleUploadConfig);

  server.on(
    "/api/config/download",
    HTTP_GET,
    handleDownloadConfig);

  server.on(
    "/api/artnet/poll",
    HTTP_POST,
    handlePollArtNetSubscribers);

  server.on(
    "/api/artnet/subscribers",
    HTTP_GET,
    handleArtNetSubscribers);

  server.on(
    "/api/dmx",
    HTTP_POST,
    handleDmxValue);

  server.on(
    "/api/dmx/release",
    HTTP_POST,
    handleReleaseDmxOverride);

  server.on(
    "/api/dmx/timeout",
    HTTP_POST,
    handleDmxOverrideTimeout);

  server.on(
    "/api/failsafe/record",
    HTTP_POST,
    handleRecordFailsafeScene);

  server.on(
    "/api/update/firmware",
    HTTP_POST,
    handleFirmwareUpdateComplete,
    handleFirmwareUpdateUpload);

  server.on(
    "/api/update/fs",
    HTTP_POST,
    handleFilesystemUpdateComplete,
    handleFilesystemUpdateUpload);

  server.onNotFound(
    handleNotFound);

  server.begin();

  LOG_INFO("Web server started");

  return true;
}

bool initRecoveryWeb(
  bool filesystemMounted) {
  LOG_SECTION("Recovery Web Init");

  recoveryWebMode = true;
  recoveryFilesystemMounted =
    filesystemMounted;

  server.on(
    "/",
    HTTP_GET,
    handleRecoveryPage);

  server.on(
    "/api/recovery/status",
    HTTP_GET,
    handleRecoveryStatus);

  server.on(
    "/api/recovery/auth",
    HTTP_POST,
    handleRecoveryAuthPassword);

  server.on(
    "/api/restart",
    HTTP_POST,
    handleRestart);

  server.on(
    "/api/wifi/forget",
    HTTP_POST,
    handleForgetWifiCredentials);

  server.on(
    "/api/factoryReset",
    HTTP_POST,
    handleFactoryReset);

  server.on(
    "/api/update/firmware",
    HTTP_POST,
    handleFirmwareUpdateComplete,
    handleFirmwareUpdateUpload);

  server.on(
    "/api/update/fs",
    HTTP_POST,
    handleFilesystemUpdateComplete,
    handleFilesystemUpdateUpload);

  server.onNotFound(
    handleRecoveryPage);

  server.begin();

  LOG_INFO("Recovery web server started");

  return true;
}

void updateWeb() {
  server.handleClient();

  if (restartScheduled
      && (int32_t)(millis() - restartAtMillis) >= 0) {
    LOG_INFO("Restarting now");
    ESP.restart();
  }
}
