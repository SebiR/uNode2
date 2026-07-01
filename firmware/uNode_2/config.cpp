#include "config.h"

#include <LittleFS.h>
#include <ArduinoJson.h>
#include <IPAddress.h>

#undef LOG_MODULE
#define LOG_MODULE "CFG"

Config config;

static const char* CONFIG_PATH = "/config.json";
static const char* CONFIG_TEMP_PATH = "/config.tmp";
static const char* CONFIG_BACKUP_PATH = "/config.bak";

/** @brief Populates one configuration object with factory defaults. */
static void setDefaults(Config& target) {
  target.configVersion = CONFIG_SCHEMA_VERSION;
  target.hostname = "unode";
  target.wifiMode = WIFI_MODE_AP;
  target.dhcp = true;
  target.ip = "192.168.1.50";
  target.subnet = "255.255.255.0";
  target.gateway = "192.168.1.1";
  target.ledBrightness = 50;
  target.shortName = "IN_uNode";
  target.longName = "IllumiNocte uNode";
  target.direction = ARTNET_TO_DMX;
  target.net = 0;
  target.subnetId = 0;
  target.universe = 1;
  target.failsafeMode = FAILSAFE_HOLD;
  target.mergeMode = MERGE_HTP;
  target.liveProtocol = LIVE_PROTOCOL_ARTNET;
  target.sacnSourceName = "IllumiNocte uNode";
  target.sacnPriority = 100;
  target.terminationMode = TERMINATION_AUTO;
  target.busGuardMode = BUS_GUARD_OFF;
  target.buttonShortAction = BUTTON_ACTION_DISABLED;
  target.buttonLongAction = BUTTON_ACTION_DISABLED;
  target.legacyArtPollReply = false;
  target.adminPasswordHash = "";
}

void loadDefaults() {
  setDefaults(config);
}

/** @return IPv4 address as a stable host-order 32-bit value. */
static uint32_t ipToUint32(
  const IPAddress& address) {
  return ((uint32_t)address[0] << 24)
         | ((uint32_t)address[1] << 16)
         | ((uint32_t)address[2] << 8)
         | (uint32_t)address[3];
}

/** @return True when the address is unsuitable for a station interface. */
static bool isReservedHostAddress(
  const IPAddress& address) {
  return address[0] == 0
         || address[0] == 127
         || address[0] >= 224
         || address == IPAddress(255, 255, 255, 255);
}

/** @return True when the mask consists of contiguous one bits followed by zero bits. */
static bool isContiguousSubnetMask(
  const IPAddress& subnet) {
  const uint32_t mask =
    ipToUint32(subnet);

  if (mask == 0
      || mask == 0xffffffffUL) {
    return false;
  }

  const uint32_t inverted =
    ~mask;

  return (inverted & (inverted + 1)) == 0;
}

/** @brief Validates static station IP settings and reports the first error. */
static bool validateStaticNetwork(
  const Config& candidate,
  String& error) {
  IPAddress ip;
  IPAddress subnet;
  IPAddress gateway;

  if (!ip.fromString(candidate.ip)
      || !subnet.fromString(candidate.subnet)
      || !gateway.fromString(candidate.gateway)) {
    error = "Static IP, subnet or gateway is invalid";
    return false;
  }

  if (isReservedHostAddress(ip)) {
    error = "Static IP address is reserved or multicast";
    return false;
  }

  if (isReservedHostAddress(gateway)) {
    error = "Static gateway address is reserved or multicast";
    return false;
  }

  if (!isContiguousSubnetMask(subnet)) {
    error = "Static subnet mask must be contiguous and usable";
    return false;
  }

  const uint32_t ipValue =
    ipToUint32(ip);
  const uint32_t subnetValue =
    ipToUint32(subnet);
  const uint32_t gatewayValue =
    ipToUint32(gateway);

  const uint32_t network =
    ipValue & subnetValue;
  const uint32_t broadcast =
    network | ~subnetValue;

  if (ipValue == network
      || ipValue == broadcast) {
    error = "Static IP must not be the network or broadcast address";
    return false;
  }

  if ((gatewayValue & subnetValue) != network) {
    error = "Static gateway must be in the same subnet as the IP address";
    return false;
  }

  if (gatewayValue == ipValue
      || gatewayValue == network
      || gatewayValue == broadcast) {
    error = "Static gateway must be a different usable host address";
    return false;
  }

  error = "";
  return true;
}

/** @return True when a hostname satisfies the local DNS-safe constraints. */
static bool isValidHostname(const String& hostname) {
  if (hostname.length() == 0
      || hostname.length() > 32
      || hostname[0] == '-'
      || hostname[hostname.length() - 1] == '-') {
    return false;
  }

  for (size_t i = 0; i < hostname.length(); i++) {
    const char c = hostname[i];

    if (!isAlphaNumeric(c) && c != '-') {
      return false;
    }
  }

  return true;
}

/** @return True when a stored password hash has the expected SHA1 hex shape. */
static bool isValidPasswordHash(
  const String& hash) {
  if (hash.length() == 0) {
    return true;
  }

  if (hash.length() != 40) {
    return false;
  }

  for (size_t i = 0; i < hash.length(); i++) {
    if (!isHexadecimalDigit(hash[i])) {
      return false;
    }
  }

  return true;
}

/** @brief Validates all configuration fields and reports the first error. */
static bool validateConfig(
  const Config& candidate,
  String& error) {
  if (candidate.configVersion > CONFIG_SCHEMA_VERSION) {
    error = "Configuration schema version is newer than this firmware";
    return false;
  }

  if (!isValidHostname(candidate.hostname)) {
    error = "Hostname must contain 1-32 letters, digits or hyphens";
    return false;
  }

  if (candidate.shortName.length() == 0
      || candidate.shortName.length() > 17) {
    error = "Art-Net short name must contain 1-17 characters";
    return false;
  }

  if (candidate.longName.length() == 0
      || candidate.longName.length() > 63) {
    error = "Art-Net long name must contain 1-63 characters";
    return false;
  }

  if (candidate.sacnSourceName.length() == 0
      || candidate.sacnSourceName.length() > 63) {
    error = "sACN source name must contain 1-63 characters";
    return false;
  }

  if (candidate.sacnPriority > 200) {
    error = "sACN priority must be between 0 and 200";
    return false;
  }

  if (!candidate.dhcp) {
    if (!validateStaticNetwork(
          candidate,
          error)) {
      return false;
    }
  }

  if (!isValidPasswordHash(candidate.adminPasswordHash)) {
    error = "Admin password hash is invalid";
    return false;
  }

  error = "";
  return true;
}

/** @brief Applies a JSON object to a candidate and validates the result. */
static bool applyJson(
  const JsonDocument& doc,
  Config& candidate,
  String& error) {
  if (!doc.is<JsonObjectConst>()) {
    error = "Configuration must be a JSON object";
    return false;
  }

  const int configVersion =
    doc["configVersion"] | 0;

  if (configVersion < 0
      || configVersion > CONFIG_SCHEMA_VERSION) {
    error = "Unsupported configuration schema version";
    return false;
  }

  candidate.configVersion =
    CONFIG_SCHEMA_VERSION;

  candidate.hostname =
    doc["hostname"] | candidate.hostname;

  const int wifiMode =
    doc["wifiMode"] | static_cast<int>(candidate.wifiMode);

  if (wifiMode < WIFI_MODE_CLIENT
      || wifiMode > WIFI_MODE_AP_CLIENT) {
    error = "WiFi mode must be between 0 and 2";
    return false;
  }

  candidate.wifiMode =
    static_cast<WifiMode>(wifiMode);

  candidate.dhcp =
    doc["dhcp"] | candidate.dhcp;

  candidate.ip =
    doc["ip"] | candidate.ip;

  candidate.subnet =
    doc["subnet"] | candidate.subnet;

  candidate.gateway =
    doc["gateway"] | candidate.gateway;

  const int ledBrightness =
    doc["ledBrightness"] | candidate.ledBrightness;

  if (ledBrightness < 0 || ledBrightness > 100) {
    error = "LED brightness must be between 1 and 100";
    return false;
  }

  candidate.ledBrightness =
    constrain(
      ledBrightness,
      1,
      100);

  candidate.shortName =
    doc["shortName"] | candidate.shortName;

  candidate.longName =
    doc["longName"] | candidate.longName;

  candidate.sacnSourceName =
    doc["sacnSourceName"] | candidate.sacnSourceName;

  const int direction =
    doc["direction"] | static_cast<int>(candidate.direction);

  if (direction < ARTNET_TO_DMX
      || direction > DMX_TO_ARTNET) {
    error = "Direction must be 0 or 1";
    return false;
  }

  candidate.direction =
    static_cast<Direction>(direction);

  const int net =
    doc["net"] | candidate.net;

  const int subnetId =
    doc["subnetId"] | candidate.subnetId;

  const int universe =
    doc["universe"] | candidate.universe;

  const int failsafeMode =
    doc["failsafeMode"] | static_cast<int>(candidate.failsafeMode);
  const int mergeMode =
    doc["mergeMode"] | static_cast<int>(candidate.mergeMode);
  const int liveProtocol =
    doc["liveProtocol"] | static_cast<int>(candidate.liveProtocol);
  const int sacnPriority =
    doc["sacnPriority"] | candidate.sacnPriority;
  const int terminationMode =
    doc["terminationMode"] | static_cast<int>(candidate.terminationMode);
  const int busGuardMode =
    doc["busGuardMode"] | static_cast<int>(candidate.busGuardMode);
  const int legacyButtonAction =
    doc["buttonAction"] | static_cast<int>(candidate.buttonShortAction);
  const int buttonShortAction =
    doc["buttonShortAction"] | legacyButtonAction;
  const int buttonLongAction =
    doc["buttonLongAction"] | static_cast<int>(candidate.buttonLongAction);

  if (net < 0 || net > 127) {
    error = "Art-Net net must be between 0 and 127";
    return false;
  }

  if (subnetId < 0 || subnetId > 15) {
    error = "Art-Net subnet must be between 0 and 15";
    return false;
  }

  if (universe < 0 || universe > 15) {
    error = "Art-Net universe must be between 0 and 15";
    return false;
  }

  if (failsafeMode < FAILSAFE_HOLD
      || failsafeMode > FAILSAFE_SCENE) {
    error = "Failsafe mode must be between 0 and 3";
    return false;
  }

  if (mergeMode < MERGE_HTP
      || mergeMode > MERGE_LTP) {
    error = "Merge mode must be HTP or LTP";
    return false;
  }

  if (liveProtocol < LIVE_PROTOCOL_ARTNET
      || liveProtocol > LIVE_PROTOCOL_SACN) {
    error = "Live protocol must be Art-Net or sACN";
    return false;
  }

  if (sacnPriority < 0 || sacnPriority > 200) {
    error = "sACN priority must be between 0 and 200";
    return false;
  }

  if (terminationMode < TERMINATION_OFF
      || terminationMode > TERMINATION_AUTO) {
    error = "Termination mode must be Off, On, or Auto";
    return false;
  }

  if (busGuardMode < BUS_GUARD_OFF
      || busGuardMode > BUS_GUARD_AUTO_INPUT_ON_BOOT) {
    error = "Bus guarding mode must be Off or Auto Input on Boot";
    return false;
  }

  if (buttonShortAction < BUTTON_ACTION_DISABLED
      || buttonShortAction > BUTTON_ACTION_TOGGLE_LOCATE) {
    error = "Short button action must be Disabled or Toggle Locate";
    return false;
  }

  if (buttonLongAction < BUTTON_ACTION_DISABLED
      || buttonLongAction > BUTTON_ACTION_TOGGLE_LED_MUTE) {
    error = "Long button action must be Disabled, Toggle Locate, or Toggle LED Mute";
    return false;
  }

  candidate.net = net;
  candidate.subnetId = subnetId;
  candidate.universe = universe;
  candidate.failsafeMode =
    static_cast<FailsafeMode>(failsafeMode);
  candidate.mergeMode =
    static_cast<MergeMode>(mergeMode);
  candidate.liveProtocol =
    static_cast<LiveProtocol>(liveProtocol);
  candidate.sacnPriority =
    sacnPriority;
  candidate.terminationMode =
    static_cast<TerminationMode>(terminationMode);
  candidate.busGuardMode =
    static_cast<BusGuardMode>(busGuardMode);
  candidate.buttonShortAction =
    static_cast<ButtonAction>(buttonShortAction);
  candidate.buttonLongAction =
    static_cast<ButtonAction>(buttonLongAction);

  candidate.legacyArtPollReply =
    doc["legacyArtPollReply"] | candidate.legacyArtPollReply;

  candidate.adminPasswordHash =
    doc["adminPasswordHash"] | candidate.adminPasswordHash;

  return validateConfig(candidate, error);
}

/** @brief Writes a configuration object into an ArduinoJson document. */
static void configToJsonDocument(
  const Config& source,
  JsonDocument& doc,
  bool includeSecrets = false) {
  doc["configVersion"] = CONFIG_SCHEMA_VERSION;
  doc["hostname"] = source.hostname;
  doc["wifiMode"] = source.wifiMode;
  doc["dhcp"] = source.dhcp;
  doc["ip"] = source.ip;
  doc["subnet"] = source.subnet;
  doc["gateway"] = source.gateway;
  doc["ledBrightness"] = source.ledBrightness;
  doc["shortName"] = source.shortName;
  doc["longName"] = source.longName;
  doc["direction"] = source.direction;
  doc["net"] = source.net;
  doc["subnetId"] = source.subnetId;
  doc["universe"] = source.universe;
  doc["failsafeMode"] = source.failsafeMode;
  doc["mergeMode"] = source.mergeMode;
  doc["liveProtocol"] = source.liveProtocol;
  doc["sacnSourceName"] = source.sacnSourceName;
  doc["sacnPriority"] = source.sacnPriority;
  doc["terminationMode"] = source.terminationMode;
  doc["busGuardMode"] = source.busGuardMode;
  doc["buttonAction"] = source.buttonShortAction;
  doc["buttonShortAction"] = source.buttonShortAction;
  doc["buttonLongAction"] = source.buttonLongAction;
  doc["legacyArtPollReply"] = source.legacyArtPollReply;

  if (includeSecrets
      && source.adminPasswordHash.length() > 0) {
    doc["adminPasswordHash"] =
      source.adminPasswordHash;
  }
}

bool serializeConfig(String& json) {
  JsonDocument doc;
  configToJsonDocument(
    config,
    doc,
    false);

  json = "";
  return serializeJson(doc, json) > 0;
}

/** @brief Serializes one configuration to a LittleFS file. */
static bool writeConfigFile(
  const Config& source,
  const char* path) {
  File file = LittleFS.open(path, "w");

  if (!file) {
    return false;
  }

  JsonDocument doc;
  configToJsonDocument(
    source,
    doc,
    true);

  const size_t bytesWritten =
    serializeJsonPretty(doc, file);

  file.close();
  return bytesWritten > 0;
}

/** @brief Atomically replaces config.json using temporary and backup files. */
static bool persistConfig(const Config& source) {
  LittleFS.remove(CONFIG_TEMP_PATH);

  if (!writeConfigFile(source, CONFIG_TEMP_PATH)) {
    LittleFS.remove(CONFIG_TEMP_PATH);
    return false;
  }

  const bool hadConfig =
    LittleFS.exists(CONFIG_PATH);

  LittleFS.remove(CONFIG_BACKUP_PATH);

  if (hadConfig
      && !LittleFS.rename(CONFIG_PATH, CONFIG_BACKUP_PATH)) {
    LittleFS.remove(CONFIG_TEMP_PATH);
    return false;
  }

  if (!LittleFS.rename(CONFIG_TEMP_PATH, CONFIG_PATH)) {
    if (hadConfig) {
      LittleFS.rename(CONFIG_BACKUP_PATH, CONFIG_PATH);
    }

    LittleFS.remove(CONFIG_TEMP_PATH);
    return false;
  }

  LittleFS.remove(CONFIG_BACKUP_PATH);
  return true;
}

/** @brief Parses JSON into a candidate configuration without persisting it. */
static ConfigResult parseJson(
  const String& json,
  Config& candidate,
  String& error) {
  JsonDocument doc;

  const DeserializationError jsonError =
    deserializeJson(doc, json);

  if (jsonError) {
    error = "Invalid JSON: ";
    error += jsonError.c_str();
    return ConfigResult::INVALID;
  }

  if (!applyJson(doc, candidate, error)) {
    return ConfigResult::INVALID;
  }

  return ConfigResult::OK;
}

bool loadConfig() {
  Config candidate;
  setDefaults(candidate);

  if (!LittleFS.exists(CONFIG_PATH)
      && LittleFS.exists(CONFIG_BACKUP_PATH)) {
    LittleFS.rename(
      CONFIG_BACKUP_PATH,
      CONFIG_PATH);
  }

  if (!LittleFS.exists(CONFIG_PATH)) {
    config = candidate;
    return saveConfig();
  }

  File file = LittleFS.open(CONFIG_PATH, "r");

  if (!file) {
    config = candidate;
    LOG_ERROR("Failed to open config.json");
    return false;
  }

  JsonDocument doc;
  const DeserializationError jsonError =
    deserializeJson(doc, file);

  file.close();

  String error;

  const bool hasLegacyArtNetTarget =
    !doc["artnetTargetMode"].isNull()
    || !doc["artnetTarget"].isNull()
    || !doc["preferredNode"].isNull()
    || !doc["useBroadcast"].isNull();

  const int storedConfigVersion =
    doc["configVersion"] | 0;
  const bool configSchemaMigrated =
    storedConfigVersion != CONFIG_SCHEMA_VERSION;

  if (jsonError || !applyJson(doc, candidate, error)) {
    config = candidate;
    LOG_WARN_PRINT("Invalid config.json: ");
    LOG_PRINTLN(
      LOG_LEVEL_WARN,
      jsonError ? jsonError.c_str() : error);
    return false;
  }

  config = candidate;

  if ((hasLegacyArtNetTarget || configSchemaMigrated)
      && !persistConfig(config)) {
    LOG_WARN("Failed to persist migrated configuration");
  }

  LOG_INFO("Config loaded");
  return true;
}

bool saveConfig() {
  String error;

  if (!validateConfig(config, error)) {
    LOG_WARN_PRINT("Invalid configuration: ");
    LOG_PRINTLN(
      LOG_LEVEL_WARN,
      error);
    return false;
  }

  if (!persistConfig(config)) {
    LOG_ERROR("Failed to save config.json");
    return false;
  }

  LOG_INFO("Config saved");
  return true;
}

ConfigResult updateConfigFromJson(
  const String& json,
  String& error) {
  Config candidate = config;

  const ConfigResult result =
    parseJson(json, candidate, error);

  if (result != ConfigResult::OK) {
    return result;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store configuration";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  return ConfigResult::OK;
}

/** @return Printable ASCII Art-Net name truncated to the protocol limit. */
static String sanitizeArtNetName(
  const char* value,
  size_t maximumLength) {
  String result;

  if (!value) {
    return result;
  }

  result.reserve(maximumLength);

  for (size_t i = 0;
       i < maximumLength && value[i] != '\0';
       i++) {
    const uint8_t c = value[i];
    result += (c >= 32 && c <= 126)
      ? (char)c
      : '?';
  }

  return result;
}

ConfigResult updateArtNetNames(
  const char* portName,
  const char* longName,
  bool& portNameChanged,
  bool& longNameChanged,
  String& error) {
  Config candidate = config;
  const String requestedPortName =
    sanitizeArtNetName(portName, 17);
  const String requestedLongName =
    sanitizeArtNetName(longName, 63);

  portNameChanged =
    requestedPortName.length() > 0
    && requestedPortName != candidate.shortName;
  longNameChanged =
    requestedLongName.length() > 0
    && requestedLongName != candidate.longName;

  if (!portNameChanged && !longNameChanged) {
    error = "";
    return ConfigResult::OK;
  }

  if (portNameChanged) {
    candidate.shortName = requestedPortName;
  }

  if (longNameChanged) {
    candidate.longName = requestedLongName;
  }

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store Art-Net names";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateFailsafeMode(
  FailsafeMode mode,
  String& error) {
  if (mode < FAILSAFE_HOLD
      || mode > FAILSAFE_SCENE) {
    error = "Invalid failsafe mode";
    return ConfigResult::INVALID;
  }

  if (config.failsafeMode == mode) {
    error = "";
    return ConfigResult::OK;
  }

  Config candidate = config;
  candidate.failsafeMode = mode;

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store failsafe mode";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateMergeMode(
  MergeMode mode,
  String& error) {
  if (mode < MERGE_HTP
      || mode > MERGE_LTP) {
    error = "Invalid merge mode";
    return ConfigResult::INVALID;
  }

  if (config.mergeMode == mode) {
    error = "";
    return ConfigResult::OK;
  }

  Config candidate = config;
  candidate.mergeMode = mode;

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store merge mode";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateArtNetPortAddress(
  uint8_t net,
  uint8_t subnetId,
  uint8_t universe,
  String& error) {
  if (net > 127) {
    error = "Art-Net net must be between 0 and 127";
    return ConfigResult::INVALID;
  }

  if (subnetId > 15) {
    error = "Art-Net subnet must be between 0 and 15";
    return ConfigResult::INVALID;
  }

  if (universe > 15) {
    error = "Art-Net universe must be between 0 and 15";
    return ConfigResult::INVALID;
  }

  if (config.net == net
      && config.subnetId == subnetId
      && config.universe == universe) {
    error = "";
    return ConfigResult::OK;
  }

  Config candidate = config;
  candidate.net = net;
  candidate.subnetId = subnetId;
  candidate.universe = universe;

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store Art-Net Port-Address";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateConfiguredDirection(
  Direction direction,
  String& error) {
  if (direction < ARTNET_TO_DMX
      || direction > DMX_TO_ARTNET) {
    error = "Invalid direction";
    return ConfigResult::INVALID;
  }

  if (config.direction == direction) {
    error = "";
    return ConfigResult::OK;
  }

  Config candidate = config;
  candidate.direction = direction;

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store direction";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateNetworkFromArtIpProg(
  bool enableDhcp,
  bool restoreDefaults,
  bool programIp,
  const IPAddress& ip,
  bool programSubnet,
  const IPAddress& subnet,
  bool programGateway,
  const IPAddress& gateway,
  String& error) {
  Config candidate = config;

  if (restoreDefaults) {
    Config defaults;
    setDefaults(defaults);
    candidate.dhcp = defaults.dhcp;
    candidate.ip = defaults.ip;
    candidate.subnet = defaults.subnet;
    candidate.gateway = defaults.gateway;
  }

  if (enableDhcp) {
    candidate.dhcp = true;
  } else if (programIp || programSubnet || programGateway) {
    candidate.dhcp = false;

    if (programIp) {
      candidate.ip = ip.toString();
    }

    if (programSubnet) {
      candidate.subnet = subnet.toString();
    }

    if (programGateway) {
      candidate.gateway = gateway.toString();
    }
  }

  if (candidate.dhcp == config.dhcp
      && candidate.ip == config.ip
      && candidate.subnet == config.subnet
      && candidate.gateway == config.gateway) {
    error = "";
    return ConfigResult::OK;
  }

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store network settings";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult updateAdminPasswordHash(
  const String& hash,
  String& error) {
  Config candidate = config;
  candidate.adminPasswordHash = hash;

  if (!validateConfig(candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store admin password";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

ConfigResult importConfigFile(
  const char* path,
  String& error) {
  File file = LittleFS.open(path, "r");

  if (!file) {
    error = "Failed to open uploaded configuration";
    return ConfigResult::STORAGE_ERROR;
  }

  JsonDocument doc;
  const DeserializationError jsonError =
    deserializeJson(doc, file);

  file.close();

  if (jsonError) {
    error = "Invalid JSON: ";
    error += jsonError.c_str();
    return ConfigResult::INVALID;
  }

  Config candidate;
  setDefaults(candidate);

  if (!applyJson(doc, candidate, error)) {
    return ConfigResult::INVALID;
  }

  if (!persistConfig(candidate)) {
    error = "Failed to store uploaded configuration";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  return ConfigResult::OK;
}

ConfigResult resetConfig(String& error) {
  Config candidate;
  setDefaults(candidate);

  if (!persistConfig(candidate)) {
    error = "Failed to store factory defaults";
    return ConfigResult::STORAGE_ERROR;
  }

  config = candidate;
  error = "";
  return ConfigResult::OK;
}

String getFirmwareString() {
  return String(FW_VERSION)
         + " ("
         + FW_BUILD_DATE
         + " "
         + FW_BUILD_TIME
         + ")";
}
