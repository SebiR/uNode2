#ifndef DMX_TOOL_CONFIG_H
#define DMX_TOOL_CONFIG_H

#include <Arduino.h>

// Default pins match the Raspberry Pi Pico / Arduino-Pico UART0 defaults:
//   GPIO0: Serial1 TX -> RS-485 DI or peer UART RX
//   GPIO1: Serial1 RX <- RS-485 RO or peer UART TX
#define DMX_TX_PIN 0
#define DMX_RX_PIN 1

// Set to a GPIO connected to DE/!RE if your transceiver has a direction pin.
// -1 keeps the pin unused, which is suitable for separate RX/TX transceivers
// or direct UART-to-UART bench wiring.
#define DMX_DIR_PIN -1
#define DMX_DIR_TX_LEVEL HIGH
#define DMX_DIR_RX_LEVEL LOW

static constexpr uint16_t DMX_MAX_SLOTS = 512;
static constexpr uint16_t DMX_MAX_PACKET_BYTES = DMX_MAX_SLOTS + 1;
static constexpr uint32_t DEFAULT_DMX_BAUD = 250000;
static constexpr uint32_t DEFAULT_BREAK_US = 176;
static constexpr uint32_t DEFAULT_MAB_US = 16;
static constexpr uint32_t DEFAULT_MBB_US = 0;
static constexpr uint32_t DEFAULT_TX_FPS = 40;
static constexpr uint32_t RX_BREAK_MIN_US = 88;
static constexpr uint32_t RX_FRAME_IDLE_US = 120;
static constexpr uint32_t DISPLAY_INTERVAL_MS = 1000;
static constexpr uint32_t CHANGE_HIGHLIGHT_MS = 700;
static constexpr uint16_t DEFAULT_DISPLAY_FIRST_CHANNEL = 1;
static constexpr uint16_t DEFAULT_DISPLAY_CHANNELS = 64;
static constexpr size_t DMX_UART_RX_BUFFER_SIZE = 2048;
static constexpr size_t MAX_COMMAND_LINE_LENGTH = 8192;
static constexpr const char* TOOL_VERSION = "0.1.0";

#endif
