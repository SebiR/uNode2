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
/** @return Stored station SSID, or an empty string when no credentials exist. */
String getStoredWifiSSID();
/** @return True when station credentials are currently stored in SDK flash. */
bool hasStoredWifiCredentials();
/** @brief Erases stored station credentials from SDK flash. */
bool forgetStoredWifiCredentials();

/**
 * @brief Schedules a controlled station disconnect followed by normal retry logic.
 * @param outageMillis Minimum time before the first reconnect attempt.
 * @return True when a connected Client/AP+Client interface accepted the request.
 */
bool requestClientReconnect(uint32_t outageMillis);

/** @return True when the active interface or IP configuration changed. */
bool updateNetwork();

/** @return True while the automatic recovery access point is active. */
bool isNetworkRecoveryAPActive();
/** @return True when the ESP8266 Wi-Fi mode currently includes SoftAP. */
bool isSoftAPInterfaceActive();
/** @return Number of currently associated SoftAP stations. */
uint8_t getSoftAPStationCount();
/** @return String representation of the SoftAP IP address. */
String getSoftAPIPAddress();
/** @return Current number of consecutive reconnect attempts. */
uint8_t getNetworkRetryCount();
/** @return Milliseconds since Wi-Fi connectivity was lost, or zero. */
uint32_t getNetworkDisconnectedAge();
/** @return Total station reconnect attempts since boot. */
uint32_t getNetworkReconnectAttemptCount();
/** @return Successfully completed reconnect cycles since boot. */
uint32_t getNetworkReconnectSuccessCount();
/** @return Duration of the most recently completed reconnect cycle. */
uint32_t getLastNetworkReconnectDuration();
