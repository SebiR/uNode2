#ifndef DMX_TOOL_TYPES_H
#define DMX_TOOL_TYPES_H

#include <Arduino.h>
#include "DmxToolConfig.h"

enum ToolMode {
  MODE_RX,
  MODE_TX,
  MODE_IDLE
};

enum TestPattern {
  PATTERN_STATIC,
  PATTERN_RAMP,
  PATTERN_CHASE,
  PATTERN_BLINK
};

struct RunningStats {
  uint32_t count = 0;
  uint32_t minValue = UINT32_MAX;
  uint32_t maxValue = 0;
  double sum = 0.0;

  void reset() {
    count = 0;
    minValue = UINT32_MAX;
    maxValue = 0;
    sum = 0.0;
  }

  void add(uint32_t value) {
    count++;
    minValue = min(minValue, value);
    maxValue = max(maxValue, value);
    sum += value;
  }

  uint32_t minOrZero() const {
    return count ? minValue : 0;
  }

  double average() const {
    return count ? sum / count : 0.0;
  }
};

struct AnalyzerFrame {
  uint8_t startCode = 0;
  uint16_t slots = 0;
  uint32_t breakUs = 0;
  uint32_t mabUs = 0;
  uint32_t frameToFrameUs = 0;
  uint32_t dataUs = 0;
  uint32_t completedAtMs = 0;
};

struct AnalyzerStats {
  uint32_t frames = 0;
  uint32_t shortFrames = 0;
  uint32_t longFrames = 0;
  uint32_t framingBreaks = 0;
  float fps = 0.0f;
  uint32_t fpsWindowFrames = 0;
  uint32_t fpsWindowStartMs = 0;
  RunningStats breakUs;
  RunningStats mabUs;
  RunningStats frameToFrameUs;
  RunningStats dataUs;
  RunningStats slots;

  void reset() {
    frames = 0;
    shortFrames = 0;
    longFrames = 0;
    framingBreaks = 0;
    fps = 0.0f;
    fpsWindowFrames = 0;
    fpsWindowStartMs = millis();
    breakUs.reset();
    mabUs.reset();
    frameToFrameUs.reset();
    dataUs.reset();
    slots.reset();
  }
};

#endif
