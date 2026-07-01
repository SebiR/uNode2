#pragma once

#include <Arduino.h>
#include "status_led_driver.h"

enum StatusLedMode
{
    LED_OFF = 0,
    LED_CONNECTING,
    LED_CONFIG_PORTAL,
    LED_FAULT,
    LED_READY
};

enum NetworkLedState
{
    NETWORK_DISCONNECTED = 0,
    NETWORK_ACCESS_POINT,
    NETWORK_ACCESS_POINT_CONNECTED,
    NETWORK_CONNECTED
};

enum LedIndicatorMode
{
    INDICATORS_NORMAL = 0,
    INDICATORS_MUTE,
    INDICATORS_LOCATE
};

/** @brief Initializes the configured status LED hardware. */
void initLEDs();
/** @brief Advances animations and renders both logical LEDs. */
void updateLEDs();

/** @brief Sets the high-level boot and readiness indication mode. */
void setStatusLedMode(StatusLedMode mode);
/** @brief Sets the current Wi-Fi state represented by the network LED. */
void setNetworkLedState(NetworkLedState state);
/** @brief Sets Wi-Fi signal quality in percent for connected-client indication. */
void setNetworkSignalQuality(uint8_t qualityPercent);

/** @brief Emits a short green Art-Net activity pulse. */
void flashArtNetLED();
/** @brief Emits a short cyan physical DMX input pulse. */
void flashDMXInputLED();
/** @brief Emits a short amber physical DMX output pulse. */
void flashDMXOutputLED();

/** @brief Shows a persistent alternating amber update-in-progress pattern. */
void showUpdateInProgressLEDs();
/** @brief Shows a persistent green update-success pattern until reboot. */
void showUpdateSucceededLEDs();
/** @brief Shows a short alternating red update-failed pattern. */
void showUpdateFailedLEDs();
/** @brief Shows a persistent blue/red recovery-mode warning pattern. */
void showRecoveryModeLEDs();

/** @brief Sets global LED brightness in percent in the active configuration. */
void setLEDBrightness(uint8_t brightness);

/** @brief Enables or disables Locate mode for backwards-compatible callers. */
void setLocate(bool enabled);
/** @return True while Locate mode is active. */
bool isLocateActive();
/** @brief Sets the Art-Net Normal, Mute, or Locate indicator override. */
void setLedIndicatorMode(LedIndicatorMode mode);
/** @return Current Art-Net indicator override. */
LedIndicatorMode getLedIndicatorMode();
/** @brief Mutes all status LEDs until the next reboot. */
void muteLEDsUntilReboot();
/** @return True when LEDs are currently muted by any runtime override. */
bool areLEDsMuted();

/** @brief Copies the colors most recently submitted to the LED driver. */
void getRenderedLedColors(
  StatusLedColor& networkColor,
  StatusLedColor& activityColor);
