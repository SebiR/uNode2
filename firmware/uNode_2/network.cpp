#include "network.h"
#include "config.h"
#include "leds.h"

#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiManager.h>
#include <Ticker.h>

#undef LOG_MODULE
#define LOG_MODULE "NET"

static bool mdnsStarted = false;
static Ticker configPortalLedTicker;
static bool recoveryAPActive = false;
static wl_status_t lastWifiStatus = WL_NO_SHIELD;
static IPAddress lastActiveIP;
static IPAddress lastActiveSubnet;
static IPAddress lastActiveGateway;
static uint32_t disconnectedSince = 0;
static uint32_t nextReconnectMillis = 0;
static uint32_t reconnectDelayMillis = 1000;
static uint8_t reconnectAttempts = 0;
static uint32_t lastNetworkPollMillis = 0;

static const uint32_t RECONNECT_DELAY_MIN_MS = 1000;
static const uint32_t RECONNECT_DELAY_MAX_MS = 60000;
static const uint32_t NETWORK_STATUS_POLL_INTERVAL_MS = 250;

/** @brief Advances LED animation while WiFiManager owns the main loop. */
static void updateConfigPortalLED() {
    updateLEDs();
}

/** @brief Starts the orange indicator animation for the config portal. */
static void onConfigPortalStarted(WiFiManager*) {
    LOG_INFO("WiFiManager config portal started");

    setStatusLedMode(LED_CONFIG_PORTAL);
    updateLEDs();

    // The scheduled variant executes from the cooperative Arduino context,
    // not directly from the timer interrupt (important for WS2812 output).
    configPortalLedTicker.attach_ms_scheduled(
        50,
        updateConfigPortalLED);
}

/** @brief Stops config-portal animation and restores connecting mode. */
static void stopConfigPortalLED() {
    configPortalLedTicker.detach();
    setStatusLedMode(LED_CONNECTING);
    updateLEDs();
}

/** @return True when either AP or AP+STA mode is active. */
static bool hasAccessPoint() {
    const WiFiMode_t mode = WiFi.getMode();
    return mode == WIFI_AP || mode == WIFI_AP_STA;
}

/** @return IP address of the currently preferred reachable interface. */
static IPAddress getActiveIP(wl_status_t status) {
    return status == WL_CONNECTED
        ? WiFi.localIP()
        : WiFi.softAPIP();
}

/** @return Subnet mask of the currently preferred interface. */
static IPAddress getActiveSubnet(wl_status_t status) {
    return status == WL_CONNECTED
        ? WiFi.subnetMask()
        : IPAddress(255, 255, 255, 0);
}

/** @return Gateway address of the currently preferred interface. */
static IPAddress getActiveGateway(wl_status_t status) {
    return status == WL_CONNECTED
        ? WiFi.gatewayIP()
        : WiFi.softAPIP();
}

/** @brief Maps current Wi-Fi state onto the logical network LED. */
static void updateNetworkLED(wl_status_t status) {
    if (status == WL_CONNECTED)
    {
        const int rssi =
            WiFi.RSSI();
        const uint8_t quality =
            constrain(
                2 * (rssi + 100),
                0,
                100);

        setNetworkLedState(
            NETWORK_CONNECTED);
        setNetworkSignalQuality(
            quality);
    }
    else if (hasAccessPoint())
    {
        setNetworkLedState(
            WiFi.softAPgetStationNum() > 0
                ? NETWORK_ACCESS_POINT_CONNECTED
                : NETWORK_ACCESS_POINT);
        setNetworkSignalQuality(
            100);
    }
    else
    {
        setNetworkLedState(
            NETWORK_DISCONNECTED);
        setNetworkSignalQuality(
            0);
    }
}

/** @brief Stops mDNS when it is currently running. */
static void stopMDNS() {
    if (!mdnsStarted) {
        return;
    }

    MDNS.close();
    mdnsStarted = false;
}

/** @brief Restarts mDNS on the currently reachable interface. */
static void startMDNS() {
    stopMDNS();

    if (WiFi.status() != WL_CONNECTED
        && !hasAccessPoint()) {
        return;
    }

    if (MDNS.begin(config.hostname.c_str())) {
        mdnsStarted = true;

        LOG_INFO_PRINT("mDNS started: ");
        LOG_PRINTLN(
            LOG_LEVEL_INFO,
            config.hostname + ".local");
    } else {
        LOG_WARN("mDNS failed");
    }
}

/** @brief Applies validated static station settings to WiFiManager. */
static bool configureStaticClientIP(WiFiManager& wm)
{
    IPAddress ip;
    IPAddress gateway;
    IPAddress subnet;

    if (!ip.fromString(config.ip)
        || !gateway.fromString(config.gateway)
        || !subnet.fromString(config.subnet))
    {
        LOG_WARN("Invalid static network configuration; using DHCP");
        return false;
    }

    wm.setSTAStaticIPConfig(
        ip,
        gateway,
        subnet,
        gateway);

    LOG_DEBUG_PRINT("Static IP: ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, ip);

    LOG_DEBUG_PRINT("Gateway: ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, gateway);

    LOG_DEBUG_PRINT("Subnet: ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, subnet);

    return true;
}

String getChipIdString()
{
    String chipId =
        String(ESP.getChipId(), HEX);

    chipId.toUpperCase();

    return chipId;
}

String getDefaultAPSSID()
{
    return "uNode_" + getChipIdString();
}

String getDefaultAPPassword()
{
    return "artnode" + getChipIdString();
}

String getStoredWifiSSID()
{
    return WiFi.SSID();
}

bool hasStoredWifiCredentials()
{
    return getStoredWifiSSID().length() > 0;
}

bool forgetStoredWifiCredentials()
{
    LOG_WARN("Clearing stored Wi-Fi station credentials");

    WiFi.setAutoReconnect(false);

    // WiFiManager's resetSettings() uses the ESP8266-specific persistent STA
    // erase sequence internally. A plain WiFi.disconnect(false, true) can leave
    // the saved station credentials intact on some core/library combinations.
    WiFiManager wm;
    wm.setDebugOutput(false);
    wm.resetSettings();

    // Leave the station disconnected until the scheduled restart happens.
    const bool disconnected =
        WiFi.disconnect(
            true,
            true);

    delay(250);

    return disconnected || WiFi.SSID().length() == 0;
}

String getIPAddress()
{
    if (WiFi.status() == WL_CONNECTED)
    {
        return WiFi.localIP().toString();
    }

    return WiFi.softAPIP().toString();
}

bool initNetwork()
{
    LOG_SECTION("Network Init");

    String apSSID = getDefaultAPSSID();
    String apPassword = getDefaultAPPassword();

    IPAddress apIP(2, 0, 0, 1);
    IPAddress apMask(255, 255, 255, 0);

    WiFiManager wm;

    wm.setConfigPortalTimeout(180);
    wm.setConnectTimeout(15);
    wm.setDebugOutput(false);
    wm.setAPStaticIPConfig(apIP, apIP, apMask);
    wm.setAPCallback(onConfigPortalStarted);

    // Reconnects are deliberately scheduled below so a missing AP cannot
    // cause a tight reconnect loop in the WiFi stack.
    WiFi.setAutoReconnect(false);

    if (!config.dhcp
        && config.wifiMode != WIFI_MODE_AP)
    {
        configureStaticClientIP(wm);
    }

    switch (config.wifiMode)
    {
        case WIFI_MODE_AP:
        {
            LOG_INFO("Starting AP mode");

            WiFi.mode(WIFI_AP);

            WiFi.softAPConfig(
                apIP,
                apIP,
                apMask);

            WiFi.softAP(
                apSSID.c_str(),
                apPassword.c_str());

            break;
        }

        case WIFI_MODE_AP_CLIENT:
        {
            LOG_INFO("Starting AP+Client mode");

            WiFi.mode(WIFI_AP_STA);
            WiFi.hostname(config.hostname);

            WiFi.softAPConfig(
                apIP,
                apIP,
                apMask);

            WiFi.softAP(
                apSSID.c_str(),
                apPassword.c_str());

            bool connected =
                wm.autoConnect(
                    apSSID.c_str(),
                    apPassword.c_str());

            stopConfigPortalLED();

            if (!connected)
            {
                LOG_WARN(
                    "WiFiManager timeout, AP stays active");
            }

            break;
        }

        case WIFI_MODE_CLIENT:
        default:
        {
            LOG_INFO("Starting Client mode");

            WiFi.mode(WIFI_STA);
            WiFi.hostname(config.hostname);

            bool connected =
                wm.autoConnect(
                    apSSID.c_str(),
                    apPassword.c_str());

            stopConfigPortalLED();

            if (!connected)
            {
                LOG_WARN(
                    "WiFiManager failed");
            }

            break;
        }
    }

    startMDNS();

    LOG_INFO_PRINT("IP Address: ");
    LOG_PRINTLN(LOG_LEVEL_INFO, getIPAddress());

    LOG_DEBUG_PRINT("AP SSID: ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, apSSID);

    LOG_TRACE_PRINT("AP Password: ");
    LOG_PRINTLN(LOG_LEVEL_TRACE, apPassword);

    LOG_DEBUG_PRINT("localIP = ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, WiFi.localIP());

    LOG_DEBUG_PRINT("softAPIP = ");
    LOG_PRINTLN(LOG_LEVEL_DEBUG, WiFi.softAPIP());

    const wl_status_t status = WiFi.status();
    updateNetworkLED(status);

    lastWifiStatus = status;
    lastActiveIP = getActiveIP(status);
    lastActiveSubnet = getActiveSubnet(status);
    lastActiveGateway = getActiveGateway(status);
    lastNetworkPollMillis = millis();

    if (lastWifiStatus != WL_CONNECTED
        && config.wifiMode != WIFI_MODE_AP) {
        disconnectedSince = millis();
        nextReconnectMillis = millis() + RECONNECT_DELAY_MIN_MS;
    }

    return true;
}

bool initRecoveryNetwork()
{
    LOG_SECTION("Recovery Network Init");

    const String apSSID = getDefaultAPSSID();
    const String apPassword = getDefaultAPPassword();
    const IPAddress apIP(2, 0, 0, 1);
    const IPAddress apMask(255, 255, 255, 0);

    stopMDNS();

    WiFi.disconnect(
        false,
        false);
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(apIP, apIP, apMask);

    const bool started =
        WiFi.softAP(
            apSSID.c_str(),
            apPassword.c_str());

    recoveryAPActive = started;

    updateNetworkLED(WiFi.status());

    LOG_INFO_PRINT("Recovery AP SSID: ");
    LOG_PRINTLN(LOG_LEVEL_INFO, apSSID);

    LOG_INFO_PRINT("Recovery AP IP: ");
    LOG_PRINTLN(LOG_LEVEL_INFO, WiFi.softAPIP());

    return started;
}

bool updateNetwork()
{
    const uint32_t now = millis();

    // mDNS owns a UDP receive queue and is intentionally serviced on every
    // Arduino loop pass. Wi-Fi SDK status queries are different: polling them
    // as fast as the loop can run adds no useful responsiveness and can put
    // sustained pressure on the ESP8266 radio task, especially in SoftAP mode.
    if (mdnsStarted)
    {
        MDNS.update();
    }

    if (now - lastNetworkPollMillis
        < NETWORK_STATUS_POLL_INTERVAL_MS) {
        return false;
    }

    lastNetworkPollMillis = now;
    const wl_status_t status = WiFi.status();
    bool networkChanged = false;

    if (config.wifiMode != WIFI_MODE_AP) {
        if (status == WL_CONNECTED) {
            if (lastWifiStatus != WL_CONNECTED) {
                LOG_INFO("WiFi connected");

                reconnectAttempts = 0;
                reconnectDelayMillis = RECONNECT_DELAY_MIN_MS;
                disconnectedSince = 0;
            }
        } else {
            if (lastWifiStatus == WL_CONNECTED) {
                LOG_WARN("WiFi connection lost");
                disconnectedSince = now;
                reconnectAttempts = 0;
                reconnectDelayMillis = RECONNECT_DELAY_MIN_MS;
                nextReconnectMillis = now + reconnectDelayMillis;
                stopMDNS();
            } else if (!disconnectedSince) {
                disconnectedSince = now;
            }

            if ((int32_t)(now - nextReconnectMillis) >= 0) {
                if (reconnectAttempts < UINT8_MAX) {
                    reconnectAttempts++;
                }

                LOG_INFO_PRINT("WiFi reconnect attempt ");
                LOG_PRINTLN(LOG_LEVEL_INFO, reconnectAttempts);

                WiFi.reconnect();

                reconnectDelayMillis = min(
                    reconnectDelayMillis * 2,
                    RECONNECT_DELAY_MAX_MS);
                nextReconnectMillis = now + reconnectDelayMillis;
            }
        }
    }

    const IPAddress activeIP = getActiveIP(status);
    const IPAddress activeSubnet = getActiveSubnet(status);
    const IPAddress activeGateway = getActiveGateway(status);

    if (activeIP != lastActiveIP
        || activeSubnet != lastActiveSubnet
        || activeGateway != lastActiveGateway
        || (status == WL_CONNECTED)
            != (lastWifiStatus == WL_CONNECTED)) {
        lastActiveIP = activeIP;
        lastActiveSubnet = activeSubnet;
        lastActiveGateway = activeGateway;
        networkChanged = true;

        startMDNS();
    }

    lastWifiStatus = status;
    updateNetworkLED(status);

    return networkChanged;
}

bool isNetworkRecoveryAPActive() {
    return recoveryAPActive;
}

bool isSoftAPInterfaceActive() {
    return (WiFi.getMode() & WIFI_AP) != 0;
}

uint8_t getSoftAPStationCount() {
    return WiFi.softAPgetStationNum();
}

String getSoftAPIPAddress() {
    return WiFi.softAPIP().toString();
}

uint8_t getNetworkRetryCount() {
    return reconnectAttempts;
}

uint32_t getNetworkDisconnectedAge() {
    return disconnectedSince
        ? millis() - disconnectedSince
        : 0;
}
