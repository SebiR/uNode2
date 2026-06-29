#pragma once

#include <Arduino.h>

static const uint16_t DMX_CHANNEL_COUNT = 512;

/** @brief Clears the shared 512-channel frame and initializes its version. */
void initDmxFrame();

/**
 * @brief Updates multiple channels in the shared DMX frame.
 * @param data Source channel data.
 * @param length Number of channels to copy.
 * @param clearRemaining Clear channels after length when true.
 * @return True when at least one channel changed.
 */
bool setDmxFrame(
  const uint8_t* data,
  uint16_t length,
  bool clearRemaining = false);

/**
 * @brief Updates one zero-based DMX channel.
 * @param index Zero-based channel index.
 * @param value New channel value.
 * @return True when the channel changed.
 */
bool setDmxChannel(
  uint16_t index,
  uint8_t value);

/** @return Value of a zero-based channel, or zero for an invalid index. */
uint8_t getDmxChannel(uint16_t index);

/** @brief Copies channels into a caller-owned buffer. */
void copyDmxFrame(
  uint8_t* destination,
  uint16_t length = DMX_CHANNEL_COUNT);

/** @return Number of meaningful channels in the effective shared frame. */
uint16_t getDmxFrameLength();

/** @return Version incremented whenever frame data changes. */
uint32_t getDmxFrameVersion();

/**
 * @brief Temporarily overrides one effective DMX channel for local testing.
 * @return True when the effective output frame changed.
 */
bool setDmxTestChannel(
  uint16_t index,
  uint8_t value);

/** @return True when an active test override was released. */
bool releaseDmxTestOverride();

/** @return True when the test override is currently active. */
bool isDmxTestOverrideActive();

/** @brief Enables or disables automatic expiry of the local test override. */
void setDmxTestOverrideTimeoutEnabled(bool enabled);

/** @return True when the local test override expires automatically. */
bool isDmxTestOverrideTimeoutEnabled();

/** @return Milliseconds until the test override expires, or zero. */
uint32_t getDmxTestOverrideRemaining();

/** @return True when a previously active test override expired now. */
bool updateDmxTestOverride();
