#pragma once

#include <Arduino.h>

enum class StatusLedColor : uint8_t {
  OFF,
  RED,
  ORANGE,
  GREEN,
  BLUE,
  CYAN,
  YELLOW,
  MAGENTA
};

/** @brief One arbitrary RGB color for direct status LED rendering. */
struct StatusLedRgb {
  uint8_t red;
  uint8_t green;
  uint8_t blue;
};

/** @return RGB representation of one predefined logical status color. */
StatusLedRgb statusLedColorToRgb(
  StatusLedColor color);

/** @brief Initializes the selected physical status LED backend. */
void initStatusLedDriver();

/**
 * @brief Renders both logical LEDs on the configured hardware.
 * @param statusColor Network/status LED color.
 * @param artnetColor Art-Net/DMX activity LED color.
 * @param brightness Global brightness in percent.
 */
void renderStatusLeds(
  StatusLedColor statusColor,
  StatusLedColor artnetColor,
  uint8_t brightness);

/**
 * @brief Renders arbitrary RGB values on both logical LEDs.
 *
 * Legacy single-color hardware treats black as off and every other RGB value
 * as on. Current WS2812 hardware renders the requested colors exactly.
 *
 * @param statusColor Network/status LED RGB color.
 * @param artnetColor Art-Net/DMX activity LED RGB color.
 * @param brightness Global brightness in percent.
 */
void renderStatusLedsRgb(
  StatusLedRgb statusColor,
  StatusLedRgb artnetColor,
  uint8_t brightness);
