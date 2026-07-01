#include "leds.h"

#include "config.h"
#include "status_led_driver.h"

static StatusLedMode statusMode = LED_OFF;
static NetworkLedState networkState =
  NETWORK_DISCONNECTED;
static uint8_t networkSignalQuality = 100;

static uint32_t lastStatusBlink = 0;
static bool statusBlinkState = false;

static uint32_t artnetFlashUntil = 0;
static StatusLedColor activityColor =
  StatusLedColor::OFF;

enum SystemLedPattern
{
    SYSTEM_PATTERN_NONE = 0,
    SYSTEM_PATTERN_UPDATE_PROGRESS,
    SYSTEM_PATTERN_UPDATE_SUCCESS,
    SYSTEM_PATTERN_UPDATE_FAILED,
    SYSTEM_PATTERN_RECOVERY
};

static SystemLedPattern systemPattern =
  SYSTEM_PATTERN_NONE;
static uint32_t systemPatternUntil = 0;

static LedIndicatorMode indicatorMode =
  INDICATORS_NORMAL;
static bool muteUntilReboot = false;
static uint32_t locateLastToggle = 0;
static bool locateState = false;

static StatusLedColor renderedNetworkColor =
  StatusLedColor::OFF;
static StatusLedColor renderedActivityColor =
  StatusLedColor::OFF;

void initLEDs() {
  initStatusLedDriver();
}

void setStatusLedMode(
  StatusLedMode mode) {
  statusMode = mode;
}

void setNetworkLedState(
  NetworkLedState state) {
  networkState = state;
}

void setNetworkSignalQuality(
  uint8_t qualityPercent) {
  networkSignalQuality =
    constrain(
      qualityPercent,
      0,
      100);
}

/** @brief Starts or extends a short activity pulse with the given color. */
static void flashActivityLED(
  StatusLedColor color) {
  activityColor = color;
  artnetFlashUntil =
    millis() + 50;
}

void flashArtNetLED() {
  flashActivityLED(
    StatusLedColor::GREEN);
}

void flashDMXInputLED() {
  flashActivityLED(
    StatusLedColor::CYAN);
}

void flashDMXOutputLED() {
  flashActivityLED(
    StatusLedColor::ORANGE);
}

static void setSystemLedPattern(
  SystemLedPattern pattern,
  uint32_t durationMs = 0) {
  systemPattern = pattern;
  systemPatternUntil =
    durationMs > 0
      ? millis() + durationMs
      : 0;
}

void showUpdateInProgressLEDs() {
  setSystemLedPattern(
    SYSTEM_PATTERN_UPDATE_PROGRESS);
}

void showUpdateSucceededLEDs() {
  setSystemLedPattern(
    SYSTEM_PATTERN_UPDATE_SUCCESS);
}

void showUpdateFailedLEDs() {
  setSystemLedPattern(
    SYSTEM_PATTERN_UPDATE_FAILED,
    2500);
}

void showRecoveryModeLEDs() {
  setSystemLedPattern(
    SYSTEM_PATTERN_RECOVERY);
}

void setLocate(bool enabled) {
  setLedIndicatorMode(
    enabled
      ? INDICATORS_LOCATE
      : INDICATORS_NORMAL);
}

void setLedIndicatorMode(LedIndicatorMode mode) {
  indicatorMode = mode;

  if (mode == INDICATORS_LOCATE) {
    locateLastToggle = millis();
    locateState = false;
  }
}

bool isLocateActive() {
  return indicatorMode == INDICATORS_LOCATE;
}

LedIndicatorMode getLedIndicatorMode() {
  return indicatorMode;
}

void muteLEDsUntilReboot() {
  muteUntilReboot = true;
}

bool areLEDsMuted() {
  return muteUntilReboot
         || indicatorMode == INDICATORS_MUTE;
}

void getRenderedLedColors(
  StatusLedColor& networkColor,
  StatusLedColor& activityLedColor) {
  networkColor = renderedNetworkColor;
  activityLedColor = renderedActivityColor;
}

void setLEDBrightness(
  uint8_t brightness) {
  config.ledBrightness =
    constrain(
      brightness,
      0,
      100);
}

/** @return Network/status LED color for the current logical state. */
static StatusLedColor getStatusColor(
  uint32_t now) {
  switch (statusMode) {
    case LED_READY:
      switch (networkState) {
        case NETWORK_CONNECTED:
#if USE_WS2812
          if (networkSignalQuality < 25) {
            return (now % 2000) < 200
              ? StatusLedColor::RED
              : StatusLedColor::GREEN;
          }

          if (networkSignalQuality < 50) {
            return (now % 2000) < 200
              ? StatusLedColor::ORANGE
              : StatusLedColor::GREEN;
          }

          return StatusLedColor::GREEN;
#else
          if (networkSignalQuality < 25) {
            return (now % 2000) < 200
              ? StatusLedColor::GREEN
              : StatusLedColor::OFF;
          }

          if (networkSignalQuality < 50) {
            return (now % 2000) < 200
              ? StatusLedColor::OFF
              : StatusLedColor::GREEN;
          }

          return StatusLedColor::GREEN;
#endif

        case NETWORK_ACCESS_POINT_CONNECTED:
#if USE_WS2812
          return StatusLedColor::BLUE;
#else
          return StatusLedColor::GREEN;
#endif

        case NETWORK_ACCESS_POINT:
          return (now % 1000) < 200
            ? StatusLedColor::BLUE
            : StatusLedColor::OFF;


        case NETWORK_DISCONNECTED:
        default:
          return StatusLedColor::RED;
      }

    case LED_CONNECTING:
      if (now - lastStatusBlink >= 500) {
        lastStatusBlink = now;
        statusBlinkState = !statusBlinkState;
      }

      return statusBlinkState
        ? StatusLedColor::RED
        : StatusLedColor::OFF;

    case LED_CONFIG_PORTAL:
      if (now - lastStatusBlink >= 150) {
        lastStatusBlink = now;
        statusBlinkState = !statusBlinkState;
      }

      return statusBlinkState
        ? StatusLedColor::ORANGE
        : StatusLedColor::OFF;

    case LED_FAULT:
      if (now - lastStatusBlink >= 120) {
        lastStatusBlink = now;
        statusBlinkState = !statusBlinkState;
      }

      return statusBlinkState
        ? StatusLedColor::RED
        : StatusLedColor::OFF;

    case LED_OFF:
    default:
      return StatusLedColor::OFF;
  }
}

/** @brief Renders one pair of logical LED colors and stores them for WebSocket mirroring. */
static void renderLogicalColors(
  StatusLedColor networkColor,
  StatusLedColor activityLedColor) {
  renderedNetworkColor = networkColor;
  renderedActivityColor = activityLedColor;

  renderStatusLeds(
    networkColor,
    activityLedColor,
    config.ledBrightness);
}

/** @return True when a temporary or persistent system pattern was rendered. */
static bool renderSystemPattern(
  uint32_t now) {
  if (systemPattern == SYSTEM_PATTERN_NONE) {
    return false;
  }

  if (systemPatternUntil > 0
      && (int32_t)(now - systemPatternUntil) >= 0) {
    systemPattern =
      SYSTEM_PATTERN_NONE;
    systemPatternUntil = 0;
    return false;
  }

  const bool phase =
    (now % 400) < 200;

  switch (systemPattern) {
    case SYSTEM_PATTERN_UPDATE_PROGRESS:
      renderLogicalColors(
        phase
          ? StatusLedColor::ORANGE
          : StatusLedColor::OFF,
        phase
          ? StatusLedColor::OFF
          : StatusLedColor::ORANGE);
      return true;

    case SYSTEM_PATTERN_UPDATE_SUCCESS:
      renderLogicalColors(
        StatusLedColor::GREEN,
        StatusLedColor::GREEN);
      return true;

    case SYSTEM_PATTERN_UPDATE_FAILED:
      renderLogicalColors(
        phase
          ? StatusLedColor::RED
          : StatusLedColor::OFF,
        phase
          ? StatusLedColor::OFF
          : StatusLedColor::RED);
      return true;

    case SYSTEM_PATTERN_RECOVERY:
      renderLogicalColors(
        phase
          ? StatusLedColor::BLUE
          : StatusLedColor::RED,
        phase
          ? StatusLedColor::RED
          : StatusLedColor::BLUE);
      return true;

    case SYSTEM_PATTERN_NONE:
    default:
      return false;
  }
}

void updateLEDs() {
  const uint32_t now = millis();

  if (renderSystemPattern(now)) {
    return;
  }

  if (areLEDsMuted()) {
    renderLogicalColors(
      StatusLedColor::OFF,
      StatusLedColor::OFF);

    return;
  }

  if (indicatorMode == INDICATORS_LOCATE) {
    if (now - locateLastToggle >= 150) {
      locateLastToggle = now;
      locateState = !locateState;
    }

    const StatusLedColor locateColor =
      locateState
        ? StatusLedColor::MAGENTA
        : StatusLedColor::OFF;

    renderLogicalColors(
      locateColor,
      locateColor);

    return;
  }

  const StatusLedColor statusColor =
    getStatusColor(now);

  const StatusLedColor artnetColor =
    now < artnetFlashUntil
      ? activityColor
      : StatusLedColor::OFF;

  renderLogicalColors(
    statusColor,
    artnetColor);
}
