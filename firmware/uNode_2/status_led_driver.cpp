#include "status_led_driver.h"

#include "config.h"

#if USE_WS2812

#include <Adafruit_NeoPixel.h>

static Adafruit_NeoPixel pixels(
  LED_WS2812_COUNT,
  LED_WS2812_PIN,
  LED_WS2812_COLOR_ORDER + NEO_KHZ800);

/** @return NeoPixel-packed RGB value for one logical status color. */
static uint32_t getPixelColor(
  StatusLedColor color) {
  switch (color) {
    case StatusLedColor::RED:
      return pixels.Color(255, 0, 0);

    case StatusLedColor::ORANGE:
      return pixels.Color(255, 80, 0);

    case StatusLedColor::GREEN:
      return pixels.Color(0, 255, 0);

    case StatusLedColor::BLUE:
      return pixels.Color(0, 0, 255);

    case StatusLedColor::CYAN:
      return pixels.Color(0, 255, 255);

    case StatusLedColor::YELLOW:
      return pixels.Color(255, 255, 0);

    case StatusLedColor::MAGENTA:
      return pixels.Color(255, 0, 255);

    case StatusLedColor::OFF:
    default:
      return pixels.Color(0, 0, 0);
  }
}

void initStatusLedDriver() {
  pixels.begin();
  pixels.clear();
  pixels.show();
}

void renderStatusLeds(
  StatusLedColor statusColor,
  StatusLedColor artnetColor,
  uint8_t brightness) {
  static StatusLedColor lastStatusColor =
    StatusLedColor::OFF;
  static StatusLedColor lastArtnetColor =
    StatusLedColor::OFF;
  static uint8_t lastBrightness = 255;

  brightness = constrain(brightness, 0, 100);

  if (statusColor == lastStatusColor
      && artnetColor == lastArtnetColor
      && brightness == lastBrightness) {
    return;
  }

  lastStatusColor = statusColor;
  lastArtnetColor = artnetColor;
  lastBrightness = brightness;

  pixels.setBrightness(
    map(brightness, 0, 100, 0, 255));

  pixels.setPixelColor(
    LED_WS2812_STATUS_INDEX,
    getPixelColor(statusColor));

  pixels.setPixelColor(
    LED_WS2812_ARTNET_INDEX,
    getPixelColor(artnetColor));

  pixels.show();
}

#else

/** @brief Writes one legacy LED using PWM or digital output. */
static void writeLegacyLED(
  uint8_t pin,
  bool enabled,
  uint8_t brightness) {
#if USE_LED_PWM
  const uint16_t value =
    enabled
      ? map(
          constrain(brightness, 0, 100),
          0,
          100,
          0,
          1023)
      : 0;

  analogWrite(pin, value);
#else
  digitalWrite(
    pin,
    enabled && brightness > 0
      ? HIGH
      : LOW);
#endif
}

void initStatusLedDriver() {
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(LED_ARTNET_PIN, OUTPUT);

#if USE_LED_PWM
  analogWriteRange(1023);
#endif

  writeLegacyLED(
    LED_STATUS_PIN,
    false,
    0);

  writeLegacyLED(
    LED_ARTNET_PIN,
    false,
    0);
}

void renderStatusLeds(
  StatusLedColor statusColor,
  StatusLedColor artnetColor,
  uint8_t brightness) {
  static StatusLedColor lastStatusColor =
    StatusLedColor::MAGENTA;
  static StatusLedColor lastArtnetColor =
    StatusLedColor::MAGENTA;
  static uint8_t lastBrightness = 255;

  brightness = constrain(brightness, 0, 100);

  if (statusColor == lastStatusColor
      && artnetColor == lastArtnetColor
      && brightness == lastBrightness) {
    return;
  }

  lastStatusColor = statusColor;
  lastArtnetColor = artnetColor;
  lastBrightness = brightness;

  writeLegacyLED(
    LED_STATUS_PIN,
    statusColor != StatusLedColor::OFF,
    brightness);

  writeLegacyLED(
    LED_ARTNET_PIN,
    artnetColor != StatusLedColor::OFF,
    brightness);
}

#endif
