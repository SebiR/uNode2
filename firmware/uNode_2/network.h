#pragma once

#include <Arduino.h>
#include "config.h"

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

#if ENABLE_TEST_HARNESS_API
/**
 * @brief Schedules a controlled station disconnect followed by normal retry logic.
 * @param outageMillis Minimum time before the first reconnect attempt.
 * @return True when a connected Client/AP+Client interface accepted the request.
 */
bool requestClientReconnect(uint32_t outageMillis);

/**
 * @brief Schedules a non-persistent Client connection for the test fixture.
 * @param ssid Temporary access-point SSID (1..32 bytes).
 * @param password Empty for an open network or 8..63 bytes for WPA2.
 * @param switchDelayMillis Delay that lets the HTTP response reach the caller.
 * @param connectTimeoutMillis Time before restoring the configured AP mode.
 * @return True when the temporary request was accepted.
 */
bool requestTemporaryTestClient(
  const char* ssid,
  const char* password,
  uint32_t switchDelayMillis,
  uint32_t connectTimeoutMillis);

/** @return True while temporary test credentials own the station interface. */
bool isTemporaryTestClientActive();

/** @brief Quiesces the volatile station interface before ESP.restart(). */
void prepareTemporaryTestClientRestart();
#endif

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
