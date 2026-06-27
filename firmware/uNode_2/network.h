#pragma once

#include <Arduino.h>

/** @brief Initializes the configured Wi-Fi mode and mDNS service. */
bool initNetwork();

/** @brief Starts the firmware-embedded recovery access point. */
bool initRecoveryNetwork();

/** @return String representation of the currently reachable interface IP. */
String getIPAddress();

/** @return Uppercase hexadecimal ESP8266 chip identifier. */
String getChipIdString();

/** @return Deterministic access-point SSID for this device. */
String getDefaultAPSSID();
/** @return Deterministic access-point password for this device. */
String getDefaultAPPassword();

/** @return True when the active interface or IP configuration changed. */
bool updateNetwork();

/** @return True while the automatic recovery access point is active. */
bool isNetworkRecoveryAPActive();
/** @return Current number of consecutive reconnect attempts. */
uint8_t getNetworkRetryCount();
/** @return Milliseconds since Wi-Fi connectivity was lost, or zero. */
uint32_t getNetworkDisconnectedAge();
