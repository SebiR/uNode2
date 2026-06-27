#include "dmx_frame.h"

static const uint32_t DMX_TEST_OVERRIDE_TIMEOUT_MS = 10000;

static uint8_t sourceChannels[DMX_CHANNEL_COUNT];
static uint8_t testChannels[DMX_CHANNEL_COUNT];
static uint32_t frameVersion = 0;
static bool testOverrideActive = false;
static uint32_t testOverrideUntilMillis = 0;

/** @brief Advances the frame version while reserving zero. */
static void markChanged() {
  frameVersion++;

  if (frameVersion == 0) {
    frameVersion = 1;
  }
}

void initDmxFrame() {
  memset(sourceChannels, 0, sizeof(sourceChannels));
  memset(testChannels, 0, sizeof(testChannels));
  testOverrideActive = false;
  testOverrideUntilMillis = 0;
  frameVersion = 1;
}

bool updateDmxTestOverride() {
  if (!testOverrideActive
      || (int32_t)(millis() - testOverrideUntilMillis) < 0) {
    return false;
  }

  testOverrideActive = false;
  testOverrideUntilMillis = 0;
  markChanged();
  return true;
}

static const uint8_t* getEffectiveChannels() {
  updateDmxTestOverride();
  return testOverrideActive
    ? testChannels
    : sourceChannels;
}

static void beginOrExtendTestOverride() {
  updateDmxTestOverride();

  if (!testOverrideActive) {
    memcpy(
      testChannels,
      sourceChannels,
      sizeof(testChannels));
    testOverrideActive = true;
  }

  testOverrideUntilMillis =
    millis() + DMX_TEST_OVERRIDE_TIMEOUT_MS;
}

bool setDmxFrame(
  const uint8_t* data,
  uint16_t length,
  bool clearRemaining) {
  if (!data) {
    return false;
  }

  length = min(length, DMX_CHANNEL_COUNT);

  bool changed = false;

  for (uint16_t i = 0; i < length; i++) {
    if (sourceChannels[i] != data[i]) {
      sourceChannels[i] = data[i];
      changed = true;
    }
  }

  if (clearRemaining) {
    for (uint16_t i = length;
         i < DMX_CHANNEL_COUNT;
         i++) {
      if (sourceChannels[i] != 0) {
        sourceChannels[i] = 0;
        changed = true;
      }
    }
  }

  if (changed) {
    markChanged();
  }

  return changed;
}

bool setDmxChannel(
  uint16_t index,
  uint8_t value) {
  if (index >= DMX_CHANNEL_COUNT
      || sourceChannels[index] == value) {
    return false;
  }

  sourceChannels[index] = value;
  markChanged();
  return true;
}

uint8_t getDmxChannel(uint16_t index) {
  if (index >= DMX_CHANNEL_COUNT) {
    return 0;
  }

  return getEffectiveChannels()[index];
}

void copyDmxFrame(
  uint8_t* destination,
  uint16_t length) {
  if (!destination) {
    return;
  }

  length = min(length, DMX_CHANNEL_COUNT);
  memcpy(destination, getEffectiveChannels(), length);
}

uint32_t getDmxFrameVersion() {
  updateDmxTestOverride();
  return frameVersion;
}

bool setDmxTestChannel(
  uint16_t index,
  uint8_t value) {
  if (index >= DMX_CHANNEL_COUNT) {
    return false;
  }

  beginOrExtendTestOverride();

  if (testChannels[index] == value) {
    return false;
  }

  testChannels[index] = value;
  markChanged();
  return true;
}

bool releaseDmxTestOverride() {
  if (!testOverrideActive) {
    return false;
  }

  testOverrideActive = false;
  testOverrideUntilMillis = 0;
  markChanged();
  return true;
}

bool isDmxTestOverrideActive() {
  updateDmxTestOverride();
  return testOverrideActive;
}

uint32_t getDmxTestOverrideRemaining() {
  if (!isDmxTestOverrideActive()) {
    return 0;
  }

  return testOverrideUntilMillis - millis();
}
