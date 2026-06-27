#include "leds.h"

#include "config.h"
#include "status_led_driver.h"

static StatusLedMode statusMode = LED_OFF;
static NetworkLedState networkState =
  NETWORK_DISCONNECTED;

static uint32_t lastStatusBlink = 0;
static bool statusBlinkState = false;

static uint32_t artnetFlashUntil = 0;
static StatusLedColor activityColor =
  StatusLedColor::OFF;

static LedIndicatorMode indicatorMode =
  INDICATORS_NORMAL;
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
    StatusLedColor::YELLOW);
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
          return StatusLedColor::GREEN;

        case NETWORK_ACCESS_POINT:
          return StatusLedColor::BLUE;

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

void updateLEDs() {
  const uint32_t now = millis();

  if (indicatorMode == INDICATORS_MUTE) {
    renderedNetworkColor = StatusLedColor::OFF;
    renderedActivityColor = StatusLedColor::OFF;

    renderStatusLeds(
      StatusLedColor::OFF,
      StatusLedColor::OFF,
      config.ledBrightness);

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

    renderedNetworkColor = locateColor;
    renderedActivityColor = locateColor;

    renderStatusLeds(
      locateColor,
      locateColor,
      config.ledBrightness);

    return;
  }

  const StatusLedColor statusColor =
    getStatusColor(now);

  const StatusLedColor artnetColor =
    now < artnetFlashUntil
      ? activityColor
      : StatusLedColor::OFF;

  renderedNetworkColor = statusColor;
  renderedActivityColor = artnetColor;

  renderStatusLeds(
    statusColor,
    artnetColor,
    config.ledBrightness);
}
