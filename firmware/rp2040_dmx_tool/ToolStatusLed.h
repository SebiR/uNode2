#ifndef TOOL_STATUS_LED_H
#define TOOL_STATUS_LED_H

#include <Adafruit_NeoPixel.h>
#include <Arduino.h>

#include "DmxToolConfig.h"
#include "DmxToolTypes.h"

/** @brief Non-blocking status indication for the RP2040 DMX test fixture. */
class ToolStatusLed {
public:
  ToolStatusLed();

  /** @brief Initializes the onboard WS2812 and starts the boot indication. */
  void begin();
  /** @brief Schedules a visible receive-activity pulse. */
  void notifyRxFrame();
  /** @brief Schedules a visible transmit-activity pulse. */
  void notifyTxFrame();
  /** @brief Overrides the current state with a short red error indication. */
  void notifyError();

  /**
   * @brief Advances the LED animation without blocking DMX processing.
   *
   * @param mode Current tool mode.
   * @param txEnabled True while continuous DMX transmission is active.
   * @param safeToShow False while the analyzer is inside an RX frame.
   */
  void update(
    ToolMode mode,
    bool txEnabled,
    bool safeToShow);

private:
  Adafruit_NeoPixel pixel;
  uint32_t bootUntilMs = 0;
  uint32_t errorUntilMs = 0;
  uint32_t activityUntilMs = 0;
  uint32_t nextActivityPulseMs = 0;
  uint32_t nextUpdateMs = 0;
  uint32_t lastColor = UINT32_MAX;
  bool pendingRxActivity = false;
  bool pendingTxActivity = false;

  /** @brief Writes one RGB value only when it differs from the last output. */
  void showColor(
    uint8_t red,
    uint8_t green,
    uint8_t blue);
};

#endif
