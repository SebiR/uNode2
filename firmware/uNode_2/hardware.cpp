#include <Arduino.h>

#include "hardware.h"

#undef LOG_MODULE
#define LOG_MODULE "HW"

static bool rs485DriverEnabled = false;
static bool rs485ReceiverEnabled = false;
static bool terminationEnabled = false;

/** @brief Applies the effective RS-485 direction pins for the current build. */
static void applyRs485DirectionPins() {
#if ENABLE_RS485_SPLIT_CONTROL
  rs485DriverEnabled =
    config.direction == ARTNET_TO_DMX;
  rs485ReceiverEnabled =
    config.direction == DMX_TO_ARTNET;

  digitalWrite(
    PIN_RS485_DE,
    rs485DriverEnabled ? HIGH : LOW);

  digitalWrite(
    PIN_RS485_RE,
    rs485ReceiverEnabled ? LOW : HIGH);
#else
  rs485DriverEnabled =
    config.direction == ARTNET_TO_DMX;
  rs485ReceiverEnabled =
    config.direction == DMX_TO_ARTNET;

  digitalWrite(
    PIN_RS485_DIR,
    rs485DriverEnabled ? HIGH : LOW);
#endif
}

void initHardware() {
#if ENABLE_RS485_SPLIT_CONTROL
  pinMode(
    PIN_RS485_RE,
    OUTPUT);

  pinMode(
    PIN_RS485_DE,
    OUTPUT);

  // Safe passive default: driver disabled and receiver disabled.
  digitalWrite(
    PIN_RS485_DE,
    LOW);

  digitalWrite(
    PIN_RS485_RE,
    HIGH);
#else
  pinMode(
    PIN_RS485_DIR,
    OUTPUT);
#endif

#if ENABLE_RS485_TERMINATION_CONTROL
  pinMode(
    PIN_RS485_TERMINATION,
    OUTPUT);

  digitalWrite(
    PIN_RS485_TERMINATION,
    LOW);
#endif

  LOG_INFO("Hardware GPIOs initialized in passive state");
}

void applyHardwareForDirection() {
  applyRs485DirectionPins();
  applyTermination();

  LOG_DEBUG_PRINT("RS485 driver: ");
  LOG_PRINTLN(
    LOG_LEVEL_DEBUG,
    rs485DriverEnabled ? "enabled" : "disabled");

  LOG_DEBUG_PRINT("RS485 receiver: ");
  LOG_PRINTLN(
    LOG_LEVEL_DEBUG,
    rs485ReceiverEnabled ? "enabled" : "disabled");
}

void applyHardwareListenOnly() {
  rs485DriverEnabled = false;
  rs485ReceiverEnabled = true;

#if ENABLE_RS485_SPLIT_CONTROL
  digitalWrite(
    PIN_RS485_DE,
    LOW);

  digitalWrite(
    PIN_RS485_RE,
    LOW);
#else
  digitalWrite(
    PIN_RS485_DIR,
    LOW);
#endif

#if ENABLE_RS485_TERMINATION_CONTROL
  terminationEnabled =
    config.terminationMode != TERMINATION_OFF;

  digitalWrite(
    PIN_RS485_TERMINATION,
    terminationEnabled ? HIGH : LOW);
#else
  terminationEnabled = false;
#endif

  LOG_DEBUG("RS485 listen-only guard mode enabled");
}

void applyTermination() {
#if ENABLE_RS485_TERMINATION_CONTROL
  switch (config.terminationMode) {
    case TERMINATION_ON:
      terminationEnabled = true;
      break;

    case TERMINATION_AUTO:
      terminationEnabled =
        config.direction == DMX_TO_ARTNET;
      break;

    case TERMINATION_OFF:
    default:
      terminationEnabled = false;
      break;
  }

  digitalWrite(
    PIN_RS485_TERMINATION,
    terminationEnabled ? HIGH : LOW);
#else
  terminationEnabled = false;
#endif

  LOG_DEBUG_PRINT("RS485 termination: ");
  LOG_PRINTLN(
    LOG_LEVEL_DEBUG,
    terminationEnabled ? "enabled" : "disabled");
}

bool isRs485SplitControlSupported() {
#if ENABLE_RS485_SPLIT_CONTROL
  return true;
#else
  return false;
#endif
}

bool isTerminationControlSupported() {
#if ENABLE_RS485_TERMINATION_CONTROL
  return true;
#else
  return false;
#endif
}

bool isRs485DriverEnabled() {
  return rs485DriverEnabled;
}

bool isRs485ReceiverEnabled() {
  return rs485ReceiverEnabled;
}

bool isTerminationEnabled() {
  return terminationEnabled;
}
