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
