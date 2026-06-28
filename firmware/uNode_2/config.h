#pragma once

#include <Arduino.h>
#include <IPAddress.h>

// -----------------------------------------------------------------------------
// Firmware
// -----------------------------------------------------------------------------

#define FW_VERSION_MAJOR 0
#define FW_VERSION_MINOR 19
#define FW_VERSION_PATCH 4

#define FW_STRINGIFY_IMPL(value) #value
#define FW_STRINGIFY(value) FW_STRINGIFY_IMPL(value)
#define FW_VERSION \
  FW_STRINGIFY(FW_VERSION_MAJOR) "." \
  FW_STRINGIFY(FW_VERSION_MINOR) "." \
  FW_STRINGIFY(FW_VERSION_PATCH)

#define FW_BUILD_DATE __DATE__
#define FW_BUILD_TIME __TIME__

#define FW_FLASH_LAYOUT "4M1M"
#define FW_LITTLEFS_IMAGE_SIZE 0xFA000UL
#define FW_WEB_ASSET_VERSION FW_VERSION
#define CONFIG_SCHEMA_VERSION 2

// -----------------------------------------------------------------------------
// Feature Switches
// -----------------------------------------------------------------------------

#ifndef ENABLE_DEBUG
#define ENABLE_DEBUG 1
#endif

// Serial logging is disabled by default. When enabled, logs use UART1 TX
// (Serial1 on GPIO2) so UART0 remains available for DMX.
#ifndef ENABLE_SERIAL_LOG
#define ENABLE_SERIAL_LOG ENABLE_DEBUG
#endif

#ifndef LOG_SERIAL_PORT
#define LOG_SERIAL_PORT Serial1
#endif

#ifndef LOG_SERIAL_BAUD
#define LOG_SERIAL_BAUD 115200
#endif

// Set this explicitly when LOG_SERIAL_PORT is changed to Serial/UART0.
#ifndef SERIAL_LOG_REPLACES_DMX
#define SERIAL_LOG_REPLACES_DMX 0
#endif

// 0: two classic status LEDs, 1: two WS2812/SK6812-compatible pixels
#ifndef USE_WS2812
#define USE_WS2812 1
#endif

// Legacy LEDs only: 0 saves IRAM and uses digital on/off, 1 enables brightness
#ifndef USE_LED_PWM
#define USE_LED_PWM 1
#endif

// -----------------------------------------------------------------------------
// GPIO Assignment
// -----------------------------------------------------------------------------

#ifndef ENABLE_RS485_SPLIT_CONTROL
#define ENABLE_RS485_SPLIT_CONTROL USE_WS2812
#endif

#ifndef ENABLE_RS485_TERMINATION_CONTROL
#define ENABLE_RS485_TERMINATION_CONTROL ENABLE_RS485_SPLIT_CONTROL
#endif

#define PIN_RS485_DIR 5
#define PIN_RS485_RE 5
#define PIN_RS485_DE 12
#define PIN_RS485_TERMINATION 13

#ifndef PIN_RECOVERY_BUTTON
#define PIN_RECOVERY_BUTTON 14
#endif

#ifndef ENABLE_BOOT_RECOVERY_BUTTON
#define ENABLE_BOOT_RECOVERY_BUTTON 1
#endif

#define LED_ARTNET_PIN 12
#define LED_STATUS_PIN 13

#define LED_WS2812_PIN 4
#define LED_WS2812_COUNT 2
#define LED_WS2812_STATUS_INDEX 0
#define LED_WS2812_ARTNET_INDEX 1

// Adafruit NeoPixel color order, e.g. NEO_GRB, NEO_RGB or NEO_BRG
#ifndef LED_WS2812_COLOR_ORDER
#define LED_WS2812_COLOR_ORDER NEO_RGB
#endif

//#define DIRECTION_ARTNET_TO_DMX 0
//#define DIRECTION_DMX_TO_ARTNET 1

// -----------------------------------------------------------------------------
// Logging
// -----------------------------------------------------------------------------

#define LOG_LEVEL_NONE 0
#define LOG_LEVEL_ERROR 1
#define LOG_LEVEL_WARN 2
#define LOG_LEVEL_INFO 3
#define LOG_LEVEL_DEBUG 4
#define LOG_LEVEL_TRACE 5

#ifndef LOG_MODULE
#define LOG_MODULE "SYS"
#endif

#ifndef LOG_VERBOSITY
#if ENABLE_SERIAL_LOG
#define LOG_VERBOSITY LOG_LEVEL_TRACE
#else
#define LOG_VERBOSITY LOG_LEVEL_NONE
#endif
#endif

#if ENABLE_SERIAL_LOG

#define LOG_BEGIN(baud) LOG_SERIAL_PORT.begin(baud)
#define LOG_PREFIX(severityName) \
  do { \
    LOG_SERIAL_PORT.print('['); \
    LOG_SERIAL_PORT.print(millis()); \
    LOG_SERIAL_PORT.print(F("] [")); \
    LOG_SERIAL_PORT.print(severityName); \
    LOG_SERIAL_PORT.print(F("] [")); \
    LOG_SERIAL_PORT.print(F(LOG_MODULE)); \
    LOG_SERIAL_PORT.print(F("] ")); \
  } while (0)
#define LOG_BLANK(severity) \
  do { \
    if (LOG_VERBOSITY >= (severity)) { \
      LOG_SERIAL_PORT.println(); \
    } \
  } while (0)
#define LOG_SECTION(title) \
  do { \
    if (LOG_VERBOSITY >= LOG_LEVEL_INFO) { \
      LOG_SERIAL_PORT.println(); \
      LOG_PREFIX(F("INFO")); \
      LOG_SERIAL_PORT.print(F("=== ")); \
      LOG_SERIAL_PORT.print(title); \
      LOG_SERIAL_PORT.println(F(" ===")); \
    } \
  } while (0)
#define LOG_MESSAGE(severity, severityName, value) \
  do { \
    if (LOG_VERBOSITY >= (severity)) { \
      LOG_PREFIX(severityName); \
      LOG_SERIAL_PORT.println(value); \
    } \
  } while (0)
#define LOG_LINE_START(severity, severityName, value) \
  do { \
    if (LOG_VERBOSITY >= (severity)) { \
      LOG_PREFIX(severityName); \
      LOG_SERIAL_PORT.print(value); \
    } \
  } while (0)
#define LOG_PRINT(severity, value) \
  do { \
    if (LOG_VERBOSITY >= (severity)) { \
      LOG_SERIAL_PORT.print(value); \
    } \
  } while (0)
#define LOG_PRINTLN(severity, value) \
  do { \
    if (LOG_VERBOSITY >= (severity)) { \
      LOG_SERIAL_PORT.println(value); \
    } \
  } while (0)

#else

#define LOG_BEGIN(baud) do { } while (0)
#define LOG_PREFIX(severityName) do { } while (0)
#define LOG_BLANK(severity) do { } while (0)
#define LOG_SECTION(title) do { } while (0)
#define LOG_MESSAGE(severity, severityName, value) do { } while (0)
#define LOG_LINE_START(severity, severityName, value) do { } while (0)
#define LOG_PRINT(severity, value) do { } while (0)
#define LOG_PRINTLN(severity, value) do { } while (0)

#endif

#define LOG_ERROR(value) LOG_MESSAGE(LOG_LEVEL_ERROR, F("ERROR"), value)
#define LOG_WARN(value) LOG_MESSAGE(LOG_LEVEL_WARN, F("WARN"), value)
#define LOG_INFO(value) LOG_MESSAGE(LOG_LEVEL_INFO, F("INFO"), value)
#define LOG_DEBUG(value) LOG_MESSAGE(LOG_LEVEL_DEBUG, F("DEBUG"), value)
#define LOG_TRACE(value) LOG_MESSAGE(LOG_LEVEL_TRACE, F("TRACE"), value)

#define LOG_ERROR_PRINT(value) LOG_LINE_START(LOG_LEVEL_ERROR, F("ERROR"), value)
#define LOG_WARN_PRINT(value) LOG_LINE_START(LOG_LEVEL_WARN, F("WARN"), value)
#define LOG_INFO_PRINT(value) LOG_LINE_START(LOG_LEVEL_INFO, F("INFO"), value)
#define LOG_DEBUG_PRINT(value) LOG_LINE_START(LOG_LEVEL_DEBUG, F("DEBUG"), value)
#define LOG_TRACE_PRINT(value) LOG_LINE_START(LOG_LEVEL_TRACE, F("TRACE"), value)

// Backward-compatible aliases for older code and local experiments.
#define DBG_BEGIN(baud) LOG_BEGIN(baud)
#define DBG_PRINT(value) LOG_DEBUG_PRINT(value)
#define DBG_PRINTLN(value) LOG_DEBUG(value)

// -----------------------------------------------------------------------------
// Enums
// -----------------------------------------------------------------------------

enum WifiMode {
  WIFI_MODE_CLIENT = 0,
  WIFI_MODE_AP = 1,
  WIFI_MODE_AP_CLIENT = 2
};

enum Direction {
  ARTNET_TO_DMX = 0,
  DMX_TO_ARTNET = 1
};

enum FailsafeMode {
  FAILSAFE_HOLD = 0,
  FAILSAFE_ZERO = 1,
  FAILSAFE_FULL = 2,
  FAILSAFE_SCENE = 3
};

enum MergeMode {
  MERGE_HTP = 0,
  MERGE_LTP = 1
};

enum TerminationMode {
  TERMINATION_OFF = 0,
  TERMINATION_ON = 1,
  TERMINATION_AUTO = 2
};

// -----------------------------------------------------------------------------
// Configuration Structure
// -----------------------------------------------------------------------------

struct Config {
  uint16_t configVersion;

  // Network

  String hostname;

  WifiMode wifiMode;

  bool dhcp;

  String ip;
  String subnet;
  String gateway;

  // LEDs

  uint8_t ledBrightness;

  // ArtNet

  String shortName;
  String longName;

  Direction direction;

  uint8_t net;
  uint8_t subnetId;
  uint8_t universe;

  FailsafeMode failsafeMode;

  MergeMode mergeMode;

  TerminationMode terminationMode;

  bool legacyArtPollReply;

  // Optional web UI write-protection. Empty string means authentication off.
  String adminPasswordHash;
};

enum class ConfigResult : uint8_t {
  OK,
  INVALID,
  STORAGE_ERROR
};

// -----------------------------------------------------------------------------
// Global Config Instance
// -----------------------------------------------------------------------------

extern Config config;

// -----------------------------------------------------------------------------
// Functions
// -----------------------------------------------------------------------------

/** @brief Replaces the active configuration with factory defaults in RAM. */
void loadDefaults();

/** @return True when a valid configuration was loaded from LittleFS. */
bool loadConfig();
/** @return True when the active configuration was atomically persisted. */
bool saveConfig();

/**
 * @brief Serializes the active configuration as JSON.
 * @param json Destination string.
 * @return True when serialization produced output.
 */
bool serializeConfig(String& json);

/**
 * @brief Validates, persists, and activates a JSON configuration.
 * @param json JSON object containing full or partial settings.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateConfigFromJson(
  const String& json,
  String& error);

/**
 * @brief Applies non-empty ArtAddress names and persists changed values.
 * @param portName Null-terminated Art-Net Port Name, or an empty string.
 * @param longName Null-terminated Art-Net Long Name, or an empty string.
 * @param portNameChanged Set when the Port Name changed.
 * @param longNameChanged Set when the Long Name changed.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateArtNetNames(
  const char* portName,
  const char* longName,
  bool& portNameChanged,
  bool& longNameChanged,
  String& error);

/**
 * @brief Stores a new Art-Net output failsafe mode.
 * @param mode Requested failsafe mode.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateFailsafeMode(
  FailsafeMode mode,
  String& error);

/**
 * @brief Stores a new Art-Net output merge mode.
 * @param mode Requested merge mode.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateMergeMode(
  MergeMode mode,
  String& error);

/**
 * @brief Stores a new Art-Net Port-Address.
 * @param net New Art-Net Net value, 0-127.
 * @param subnetId New Art-Net Sub-Net value, 0-15.
 * @param universe New Art-Net Universe value, 0-15.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateArtNetPortAddress(
  uint8_t net,
  uint8_t subnetId,
  uint8_t universe,
  String& error);

/**
 * @brief Stores a new Art-Net/DMX data direction.
 * @param direction Requested physical port direction.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateConfiguredDirection(
  Direction direction,
  String& error);

/**
 * @brief Stores network settings requested by ArtIpProg.
 * @param enableDhcp True to enable DHCP and ignore static fields.
 * @param restoreDefaults True to restore factory network defaults.
 * @param programIp True when ip contains a requested static IP.
 * @param ip Requested static IP address.
 * @param programSubnet True when subnet contains a requested static mask.
 * @param subnet Requested static subnet mask.
 * @param programGateway True when gateway contains a requested default gateway.
 * @param gateway Requested default gateway.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateNetworkFromArtIpProg(
  bool enableDhcp,
  bool restoreDefaults,
  bool programIp,
  const IPAddress& ip,
  bool programSubnet,
  const IPAddress& subnet,
  bool programGateway,
  const IPAddress& gateway,
  String& error);

/**
 * @brief Stores the optional admin-password hash. Empty disables web auth.
 * @param hash Hex encoded password hash, or empty.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult updateAdminPasswordHash(
  const String& hash,
  String& error);

/**
 * @brief Imports, validates, and activates a configuration file.
 * @param path LittleFS path of the uploaded file.
 * @param error Human-readable error on failure.
 * @return Result category for validation or storage.
 */
ConfigResult importConfigFile(
  const char* path,
  String& error);

/**
 * @brief Persists and activates factory defaults.
 * @param error Human-readable error on failure.
 * @return Result category for storage.
 */
ConfigResult resetConfig(String& error);

/** @return Firmware version and build timestamp for diagnostics. */
String getFirmwareString();
