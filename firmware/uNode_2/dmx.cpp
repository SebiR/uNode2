#include <LXESP8266UARTDMX.h>

#include "dmx.h"
#include "artnet.h"
#include "config.h"
#include "dmx_frame.h"
#include "hardware.h"
#include "leds.h"

#undef LOG_MODULE
#define LOG_MODULE "DMX"

static uint32_t dmxFrameCounter = 0;
static uint32_t lastDmxFrameTime = 0;
static uint32_t dmxFPS = 0;

static uint32_t fpsFrames = 0;
static uint32_t fpsTimer = 0;

static uint32_t lastOutputVersion = 0;
static uint8_t frameSnapshot[DMX_CHANNEL_COUNT];
static uint32_t lastArtNetTransmitMillis = 0;
static uint32_t lastArtNetTransmitAttemptMillis = 0;
static uint32_t lastTransmittedSubscriberVersion = 0;

static volatile uint32_t pendingInputFrames = 0;
static volatile uint32_t bootGuardInputFrames = 0;

/** @brief Attempts one subscriber-based ArtDmx transmission and records timing. */
static bool transmitArtNetFrame(uint32_t now) {
  lastArtNetTransmitAttemptMillis = now;

  if (!sendArtNetFrame()) {
    LOG_DEBUG("ArtDmx transmit skipped; no subscriber or socket unavailable");
    return false;
  }

  LOG_TRACE("ArtDmx transmitted");

  lastArtNetTransmitMillis = now;
  lastTransmittedSubscriberVersion =
    getArtNetSubscriberVersion();
  return true;
}

/** @brief ISR callback that records a completed physical DMX frame. */
static void IRAM_ATTR onDMXFrame(int slots) {
  (void)slots;
  pendingInputFrames++;
}

/** @brief ISR callback used only during the short boot bus-guard probe. */
static void IRAM_ATTR onBootGuardDMXFrame(int slots) {
  if (slots > 0) {
    bootGuardInputFrames++;
  }
}

bool applyBootBusGuard() {
  if (config.busGuardMode != BUS_GUARD_AUTO_INPUT_ON_BOOT
      || config.direction == DMX_TO_ARTNET) {
    return false;
  }

  LOG_INFO("Bus guard: listening for external DMX at boot");

  noInterrupts();
  bootGuardInputFrames = 0;
  interrupts();

  applyHardwareListenOnly();

  ESP8266DMX.setDataReceivedCallback(
    &onBootGuardDMXFrame);
  ESP8266DMX.startInput();

  const uint32_t startMillis =
    millis();

  bool detected = false;

  while (millis() - startMillis < 1200) {
    noInterrupts();
    const uint32_t frames =
      bootGuardInputFrames;
    interrupts();

    if (frames >= 2) {
      detected = true;
      break;
    }

    delay(1);
  }

  ESP8266DMX.stop();

  noInterrupts();
  bootGuardInputFrames = 0;
  pendingInputFrames = 0;
  interrupts();

  if (!detected) {
    LOG_INFO("Bus guard: no external DMX detected");
    return false;
  }

  LOG_WARN("Bus guard: external DMX detected, switching to DMX input");

  String error;
  const ConfigResult result =
    updateConfiguredDirection(
      DMX_TO_ARTNET,
      error);

  if (result != ConfigResult::OK) {
    LOG_WARN_PRINT("Bus guard direction update failed: ");
    LOG_PRINTLN(
      LOG_LEVEL_WARN,
      error);
  }

  return true;
}

bool initDMX() {
  fpsTimer = millis();

  applyHardwareForDirection();

  if (config.direction == ARTNET_TO_DMX) {
    LOG_INFO("DMX output started");
    ESP8266DMX.startOutput();
  } else {
    LOG_INFO("DMX input started");

    ESP8266DMX.setDataReceivedCallback(
      &onDMXFrame);

    ESP8266DMX.startInput();
  }

  return true;
}

bool restartDMX() {
  LOG_INFO("Restarting DMX UART");

  ESP8266DMX.stop();

  noInterrupts();
  pendingInputFrames = 0;
  interrupts();

  lastDmxFrameTime = 0;
  fpsFrames = 0;
  dmxFPS = 0;
  lastOutputVersion = 0;
  lastArtNetTransmitMillis = 0;
  lastArtNetTransmitAttemptMillis = 0;
  lastTransmittedSubscriberVersion =
    getArtNetSubscriberVersion();

  return initDMX();
}

/** @brief Copies changed shared-frame data to the UART DMX output. */
static void updateDMXOutput() {
  const uint32_t version =
    getDmxFrameVersion();

  if (version == lastOutputVersion) {
    return;
  }

  copyDmxFrame(
    frameSnapshot,
    DMX_CHANNEL_COUNT);

  ESP8266DMX.setFrame(
    frameSnapshot,
    DMX_CHANNEL_COUNT);

  lastOutputVersion = version;
}

/** @brief Moves pending UART input into the shared frame and Art-Net path. */
static void processDMXInput() {
  noInterrupts();

  const uint32_t receivedFrames =
    pendingInputFrames;

  pendingInputFrames = 0;

  interrupts();

  if (receivedFrames == 0) {
    return;
  }

  const uint16_t slots =
    ESP8266DMX.copyFrame(
      frameSnapshot,
      DMX_CHANNEL_COUNT);

  if (slots == 0) {
    return;
  }

  memset(
    frameSnapshot + slots,
    0,
    DMX_CHANNEL_COUNT - slots);

  const bool frameChanged = setDmxFrame(
    frameSnapshot,
    slots,
    true);

  dmxFrameCounter += receivedFrames;
  fpsFrames += receivedFrames;
  lastDmxFrameTime = millis();

  artnet.setPortInputActive(true);

  const uint32_t now = millis();

  if (frameChanged
      || lastArtNetTransmitAttemptMillis == 0
      || (lastArtNetTransmitMillis == 0
          && now - lastArtNetTransmitAttemptMillis >= 1000)) {
    transmitArtNetFrame(now);
  }

  flashDMXInputLED();
}

void updateDMX() {
  const bool overrideExpired =
    updateDmxTestOverride();

  if (config.direction == ARTNET_TO_DMX) {
    updateDMXOutput();
  } else {
    processDMXInput();
  }

  const uint32_t now = millis();

  const bool testOverrideActive =
    isDmxTestOverrideActive();

  const uint32_t subscriberVersion =
    getArtNetSubscriberVersion();

  if (getArtNetSubscriberCount() == 0) {
    lastTransmittedSubscriberVersion = subscriberVersion;
  }

  const bool subscriberUpdateDue =
    subscriberVersion != lastTransmittedSubscriberVersion
    && (lastArtNetTransmitAttemptMillis == 0
        || now - lastArtNetTransmitAttemptMillis >= 100);

  if (config.direction == DMX_TO_ARTNET
      && (testOverrideActive
          || overrideExpired
          || (lastDmxFrameTime > 0
              && now - lastDmxFrameTime < 2000))
      && (subscriberUpdateDue
          || overrideExpired
          || (now - lastArtNetTransmitMillis >= 1000
              && now - lastArtNetTransmitAttemptMillis >= 1000))) {
    transmitArtNetFrame(now);
  }

  if (config.direction == DMX_TO_ARTNET
      && lastDmxFrameTime > 0
      && now - lastDmxFrameTime >= 2000) {
    artnet.setPortInputActive(false);
  }

  if (now - fpsTimer >= 1000) {
    dmxFPS = fpsFrames;
    fpsFrames = 0;
    fpsTimer = now;
  }
}

uint32_t getLastDMXFrameAge() {
  if (lastDmxFrameTime == 0) {
    return 0;
  }

  return millis() - lastDmxFrameTime;
}

uint32_t getDMXFrameCounter() {
  return dmxFrameCounter;
}

uint32_t getDMXFPS() {
  return dmxFPS;
}

bool isDMXActive() {
  return lastDmxFrameTime > 0
         && millis() - lastDmxFrameTime < 2000;
}
