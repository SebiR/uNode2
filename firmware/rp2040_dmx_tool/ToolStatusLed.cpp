#include "ToolStatusLed.h"

static const uint32_t LED_UPDATE_INTERVAL_MS = 40;
static const uint32_t LED_ACTIVITY_INTERVAL_MS = 250;
static const uint32_t LED_ACTIVITY_PULSE_MS = 80;
static const uint32_t LED_ERROR_PULSE_MS = 500;
static const uint32_t LED_BOOT_PULSE_MS = 350;

ToolStatusLed::ToolStatusLed()
  : pixel(
      1,
      STATUS_LED_PIN,
      NEO_GRB + NEO_KHZ800) {
}

void ToolStatusLed::begin() {
#if STATUS_LED_PIN >= 0
  pixel.begin();
  pixel.setBrightness(STATUS_LED_BRIGHTNESS);
  pixel.clear();
  pixel.show();
  bootUntilMs = millis() + LED_BOOT_PULSE_MS;
  showColor(255, 255, 255);
#endif
}

void ToolStatusLed::notifyRxFrame() {
  pendingRxActivity = true;
}

void ToolStatusLed::notifyTxFrame() {
  pendingTxActivity = true;
}

void ToolStatusLed::notifyError() {
  errorUntilMs = millis() + LED_ERROR_PULSE_MS;
}

void ToolStatusLed::showColor(
  uint8_t red,
  uint8_t green,
  uint8_t blue) {
#if STATUS_LED_PIN >= 0
  const uint32_t color = pixel.Color(red, green, blue);

  if (color == lastColor) {
    return;
  }

  pixel.setPixelColor(0, color);
  pixel.show();
  lastColor = color;
#else
  (void)red;
  (void)green;
  (void)blue;
#endif
}

void ToolStatusLed::update(
  ToolMode mode,
  bool txEnabled,
  bool safeToShow) {
#if STATUS_LED_PIN >= 0
  const uint32_t now = millis();

  if (!safeToShow || (int32_t)(now - nextUpdateMs) < 0) {
    return;
  }

  nextUpdateMs = now + LED_UPDATE_INTERVAL_MS;

  if ((pendingRxActivity || pendingTxActivity)
      && (int32_t)(now - nextActivityPulseMs) >= 0) {
    activityUntilMs = now + LED_ACTIVITY_PULSE_MS;
    nextActivityPulseMs = now + LED_ACTIVITY_INTERVAL_MS;
    pendingRxActivity = false;
    pendingTxActivity = false;
  }

  if ((int32_t)(bootUntilMs - now) > 0) {
    showColor(255, 255, 255);
    return;
  }

  if ((int32_t)(errorUntilMs - now) > 0) {
    showColor(255, 0, 0);
    return;
  }

  if (mode == MODE_RX) {
    if ((int32_t)(activityUntilMs - now) > 0) {
      showColor(0, 255, 40);
    } else {
      showColor(0, 28, 40);
    }
    return;
  }

  if (mode == MODE_TX) {
    if (txEnabled) {
      if ((int32_t)(activityUntilMs - now) > 0) {
        showColor(255, 96, 0);
      } else {
        showColor(80, 24, 0);
      }
    } else {
      showColor(32, 10, 0);
    }
    return;
  }

  // Slow triangular blue heartbeat in idle/high-impedance mode.
  const uint16_t phase = now % 2000;
  const uint8_t level =
    phase < 1000
      ? 4 + (phase * 20 / 1000)
      : 24 - ((phase - 1000) * 20 / 1000);
  showColor(0, 0, level);
#else
  (void)mode;
  (void)txEnabled;
  (void)safeToShow;
#endif
}
