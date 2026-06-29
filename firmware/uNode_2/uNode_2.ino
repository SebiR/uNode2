#include <LittleFS.h>

#include "config.h"
#include "network.h"
#include "web.h"
#include "leds.h"
#include "artnet.h"
#include "sacn.h"
#include "websocket.h"
#include "dmx.h"
#include "dmx_frame.h"
#include "hardware.h"

#undef LOG_MODULE
#define LOG_MODULE "BOOT"

static bool recoveryBootMode = false;

/** @return True when the recovery button is held during early boot. */
static bool isRecoveryButtonHeldAtBoot() {
#if ENABLE_BOOT_RECOVERY_BUTTON
  pinMode(
    PIN_RECOVERY_BUTTON,
    INPUT_PULLUP);

  delay(20);

  if (digitalRead(PIN_RECOVERY_BUTTON) != LOW) {
    return false;
  }

  const uint32_t debounceStart =
    millis();

  while (millis() - debounceStart < 250) {
    updateLEDs();
    delay(5);
  }

  return digitalRead(PIN_RECOVERY_BUTTON) == LOW;
#else
  return false;
#endif
}

/** @brief Keeps the controller in a visible fault state until power-cycle. */
static void haltWithFilesystemFault() {
  LOG_ERROR("LittleFS mount failed; hold recovery button during boot");

  setStatusLedMode(
    LED_FAULT);

  while (true) {
    updateLEDs();
    delay(10);
  }
}

/** @brief Initializes hardware, storage, protocols, and management services. */
void setup() {
  LOG_BEGIN(LOG_SERIAL_BAUD);

  LOG_SECTION("uNode Boot");
  LOG_INFO(getFirmwareString());
  LOG_INFO_PRINT("Reset reason: ");
  LOG_PRINTLN(
    LOG_LEVEL_INFO,
    ESP.getResetReason());
  LOG_INFO_PRINT("Reset info: ");
  LOG_PRINTLN(
    LOG_LEVEL_INFO,
    ESP.getResetInfo());

  initLEDs();

  initHardware();

  setStatusLedMode(LED_CONNECTING);

  const bool recoveryRequested =
    isRecoveryButtonHeldAtBoot();

  const bool filesystemMounted =
    LittleFS.begin();

  if (recoveryRequested) {
    recoveryBootMode = true;

    loadDefaults();

    setStatusLedMode(
      LED_CONFIG_PORTAL);

    initRecoveryNetwork();
    initRecoveryWeb(filesystemMounted);

    LOG_INFO("Recovery mode ready");

    return;
  }

  if (!filesystemMounted) {
    haltWithFilesystemFault();
  }

  LOG_INFO("LittleFS mounted");

  loadConfig();

  initDmxFrame();

  randomSeed(micros());

#if !SERIAL_LOG_REPLACES_DMX
  applyBootBusGuard();
  initDMX();
#endif

  initNetwork();

  initArtNet();
  initSacn();

  initWebSocket();

  initWeb();

  setStatusLedMode(LED_READY);

  LOG_INFO("System ready");
}

/** @brief Runs all non-blocking service and protocol update functions. */
void loop() {
  if (recoveryBootMode) {
    updateLEDs();
    updateWeb();
    return;
  }

  if (updateNetwork()) {
    handleArtNetNetworkChange();
    handleSacnNetworkChange();
  }

  updateArtNet();
  updateSacn();

  updateLEDs();

  updateWebSocket();

  updateWeb();
#if !SERIAL_LOG_REPLACES_DMX
  updateDMX();
#endif
}
