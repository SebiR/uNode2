#include <Arduino.h>
#include <ArduinoJson.h>

// -----------------------------------------------------------------------------
// RP2040 DMX Analyzer / Test Sender
// -----------------------------------------------------------------------------
//
// USB Serial is used as the control terminal.
// Serial1 is used for DMX receive/transmit.
//
// Default pins match the Raspberry Pi Pico / Arduino-Pico UART0 defaults:
//   GPIO0: Serial1 TX -> RS-485 DI
//   GPIO1: Serial1 RX <- RS-485 RO
//
// If your transceiver is wired differently, adjust the definitions below.

#define DMX_TX_PIN 0
#define DMX_RX_PIN 1

// Set to a GPIO connected to DE/!RE if your transceiver has a direction pin.
// -1 keeps the pin unused, which is suitable for separate RX/TX transceivers.
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

static ToolMode mode = MODE_RX;
static TestPattern pattern = PATTERN_STATIC;

static uint8_t rxPacket[DMX_MAX_PACKET_BYTES];
static uint8_t rxValues[DMX_MAX_SLOTS];
static uint8_t previousRxValues[DMX_MAX_SLOTS];
static uint32_t rxChangeMs[DMX_MAX_SLOTS];
static uint16_t rxPacketBytes = 0;
static bool rxReceiving = false;
static bool rxSawMab = false;
static uint32_t rxFrameStartUs = 0;
static uint32_t rxBreakEndUs = 0;
static uint32_t rxDataStartUs = 0;
static uint32_t rxLastByteUs = 0;
static uint32_t rxLastFrameStartUs = 0;

static uint8_t txPacket[DMX_MAX_PACKET_BYTES];
static uint16_t txSlots = 24;
static uint32_t txBreakUs = DEFAULT_BREAK_US;
static uint32_t txMabUs = DEFAULT_MAB_US;
static uint32_t txMbbUs = DEFAULT_MBB_US;
static uint32_t txInterSlotUs = 0;
static uint32_t txBaud = DEFAULT_DMX_BAUD;
static uint32_t txFps = DEFAULT_TX_FPS;
static uint32_t nextTxMs = 0;
static uint32_t txFrames = 0;
static bool txEnabled = false;

static bool displayEnabled = false;
static bool colorEnabled = true;
static bool dirtyDisplay = true;
static uint32_t nextDisplayMs = 0;
static uint16_t displayFirstChannel = DEFAULT_DISPLAY_FIRST_CHANNEL;
static uint16_t displayChannelCount = DEFAULT_DISPLAY_CHANNELS;

static AnalyzerFrame lastFrame;
static AnalyzerStats stats;

static volatile bool edgeBreakDetected = false;
static volatile bool edgeMabDetected = false;
static volatile uint32_t edgeBreakStartUs = 0;
static volatile uint32_t edgeBreakUs = 0;
static volatile uint32_t edgeBreakEndUs = 0;
static volatile uint32_t edgeMabUs = 0;
static volatile uint32_t edgeMabEndUs = 0;
static volatile uint32_t edgeLastFallUs = 0;
static volatile uint32_t edgeLastRiseUs = 0;
static volatile bool edgeWaitingForMab = false;

static String commandLine;

static void printHelp();
static void enterRxMode(bool printLegacy = true);
static void enterTxMode(bool printLegacy = true);
static void enterIdleMode(bool printLegacy = true);
static void configureDmxSerialForRx();
static void configureDmxSerialForTx();
static void finishAnalyzerFrame();
static void flushDmxRx();
static void processJsonCommand(const String& line);
static void sendJsonReady();
static void sendJsonError(const char* error, const char* message);

static void setDirectionPin(bool transmit) {
#if DMX_DIR_PIN >= 0
  pinMode(DMX_DIR_PIN, OUTPUT);
  digitalWrite(
    DMX_DIR_PIN,
    transmit ? DMX_DIR_TX_LEVEL : DMX_DIR_RX_LEVEL);
#else
  (void)transmit;
#endif
}

static const char* modeName() {
  switch (mode) {
    case MODE_RX: return "RX analyzer";
    case MODE_TX: return "TX sender";
    case MODE_IDLE: return "idle";
  }

  return "?";
}

static const char* patternName() {
  switch (pattern) {
    case PATTERN_STATIC: return "static";
    case PATTERN_RAMP: return "ramp";
    case PATTERN_CHASE: return "chase";
    case PATTERN_BLINK: return "blink";
  }

  return "?";
}

static uint32_t clampU32(
  uint32_t value,
  uint32_t minimum,
  uint32_t maximum) {
  return min(max(value, minimum), maximum);
}

static void dmxEdgeIsr() {
  const uint32_t now = micros();
  const bool level = digitalRead(DMX_RX_PIN);

  if (!level) {
    const uint32_t highUs = now - edgeLastRiseUs;
    edgeLastFallUs = now;

    if (edgeWaitingForMab) {
      edgeMabUs = highUs;
      edgeMabEndUs = now;
      edgeMabDetected = true;
      edgeWaitingForMab = false;
    }

    return;
  }

  const uint32_t lowUs = now - edgeLastFallUs;
  edgeLastRiseUs = now;

  if (lowUs >= RX_BREAK_MIN_US) {
    edgeBreakStartUs = edgeLastFallUs;
    edgeBreakUs = lowUs;
    edgeBreakEndUs = now;
    edgeBreakDetected = true;
    edgeWaitingForMab = true;
  }
}

static void configureDmxSerialForRx() {
  Serial1.end();
  delay(2);
  setDirectionPin(false);
  pinMode(DMX_RX_PIN, INPUT_PULLUP);
  Serial1.setRX(DMX_RX_PIN);
  Serial1.setFIFOSize(DMX_UART_RX_BUFFER_SIZE);
  Serial1.begin(DEFAULT_DMX_BAUD, SERIAL_8N2);
  flushDmxRx();
  edgeLastFallUs = micros();
  edgeLastRiseUs = edgeLastFallUs;
  edgeWaitingForMab = false;
  attachInterrupt(digitalPinToInterrupt(DMX_RX_PIN), dmxEdgeIsr, CHANGE);
}

static void configureDmxSerialForTx() {
  detachInterrupt(digitalPinToInterrupt(DMX_RX_PIN));
  Serial1.end();
  delay(2);
  Serial1.setTX(DMX_TX_PIN);
  Serial1.begin(txBaud, SERIAL_8N2);
  setDirectionPin(true);
  pinMode(DMX_TX_PIN, OUTPUT);
  digitalWrite(DMX_TX_PIN, HIGH);
}

static void flushDmxRx() {
  while (Serial1.available() > 0) {
    Serial1.read();
  }
}

static void startAnalyzerFrameFromBreak(
  uint32_t breakStartUs,
  uint32_t breakEndUs,
  uint32_t breakUs) {
  rxPacketBytes = 0;
  rxReceiving = true;
  rxSawMab = false;
  rxFrameStartUs = breakStartUs;
  rxBreakEndUs = breakEndUs;
  rxDataStartUs = 0;
  rxLastByteUs = 0;
  lastFrame.breakUs = breakUs;
}

static void applyMabToCurrentFrame(
  uint32_t mabUs,
  uint32_t mabEndUs) {
  if (!rxReceiving) {
    return;
  }

  rxSawMab = true;
  rxDataStartUs = mabEndUs;
  lastFrame.mabUs = mabUs;
}

static void pollDmxRxEdges() {
  bool breakDetected = false;
  bool mabDetected = false;
  uint32_t breakStartUs = 0;
  uint32_t breakEndUs = 0;
  uint32_t breakUs = 0;
  uint32_t mabUs = 0;
  uint32_t mabEndUs = 0;

  noInterrupts();

  if (edgeBreakDetected) {
    breakDetected = true;
    breakStartUs = edgeBreakStartUs;
    breakEndUs = edgeBreakEndUs;
    breakUs = edgeBreakUs;
    edgeBreakDetected = false;
  }

  if (edgeMabDetected) {
    mabDetected = true;
    mabUs = edgeMabUs;
    mabEndUs = edgeMabEndUs;
    edgeMabDetected = false;
  }

  interrupts();

  if (breakDetected) {
    if (rxReceiving && rxPacketBytes > 0) {
      finishAnalyzerFrame();
    }

    startAnalyzerFrameFromBreak(
      breakStartUs,
      breakEndUs,
      breakUs);
  }

  if (mabDetected) {
    applyMabToCurrentFrame(
      mabUs,
      mabEndUs);
  }
}

static void updateChangedChannels(
  uint16_t slots) {
  const uint32_t now = millis();

  for (uint16_t i = 0; i < DMX_MAX_SLOTS; i++) {
    const uint8_t value =
      i < slots ? rxValues[i] : 0;

    if (value != previousRxValues[i]) {
      previousRxValues[i] = value;
      rxChangeMs[i] = now;
    }
  }
}

static void finishAnalyzerFrame() {
  if (!rxReceiving) {
    return;
  }

  rxReceiving = false;

  if (rxPacketBytes == 0) {
    return;
  }

  lastFrame.startCode = rxPacket[0];
  lastFrame.slots = rxPacketBytes - 1;
  lastFrame.completedAtMs = millis();

  for (uint16_t i = 0; i < DMX_MAX_SLOTS; i++) {
    rxValues[i] =
      i < lastFrame.slots
        ? rxPacket[i + 1]
        : 0;
  }

  lastFrame.frameToFrameUs =
    rxLastFrameStartUs == 0
      ? 0
      : rxFrameStartUs - rxLastFrameStartUs;
  rxLastFrameStartUs = rxFrameStartUs;

  lastFrame.dataUs =
    rxSawMab && rxLastByteUs > rxDataStartUs
      ? rxLastByteUs - rxDataStartUs
      : 0;

  stats.frames++;
  stats.fpsWindowFrames++;

  if (lastFrame.slots < DMX_MAX_SLOTS) {
    stats.shortFrames++;
  } else if (lastFrame.slots > DMX_MAX_SLOTS) {
    stats.longFrames++;
  }

  stats.breakUs.add(lastFrame.breakUs);
  stats.mabUs.add(lastFrame.mabUs);
  stats.slots.add(lastFrame.slots);

  if (lastFrame.frameToFrameUs > 0) {
    stats.frameToFrameUs.add(lastFrame.frameToFrameUs);
  }

  if (lastFrame.dataUs > 0) {
    stats.dataUs.add(lastFrame.dataUs);
  }

  updateChangedChannels(lastFrame.slots);
}

static void pollDmxRxBytes() {
  while (Serial1.available() > 0) {
    const int value = Serial1.read();

    if (!rxReceiving) {
      continue;
    }

    if (rxPacketBytes < DMX_MAX_PACKET_BYTES) {
      rxPacket[rxPacketBytes++] =
        static_cast<uint8_t>(value);
    }

    rxLastByteUs = micros();
  }

  if (rxReceiving
      && rxPacketBytes > 0
      && micros() - rxLastByteUs >= RX_FRAME_IDLE_US) {
    finishAnalyzerFrame();
  }
}

static void updateRxFps() {
  const uint32_t now = millis();

  if (stats.fpsWindowStartMs == 0) {
    stats.fpsWindowStartMs = now;
  }

  if (now - stats.fpsWindowStartMs >= 1000) {
    stats.fps =
      stats.fpsWindowFrames * 1000.0f /
      (now - stats.fpsWindowStartMs);
    stats.fpsWindowFrames = 0;
    stats.fpsWindowStartMs = now;
    dirtyDisplay = true;
  }
}

static void updateTxPattern() {
  static uint8_t phase = 0;
  static bool blinkOn = false;

  txPacket[0] = 0x00;

  switch (pattern) {
    case PATTERN_STATIC:
      break;

    case PATTERN_RAMP:
      for (uint16_t ch = 1; ch <= txSlots; ch++) {
        txPacket[ch] =
          static_cast<uint8_t>(phase + ch - 1);
      }
      phase++;
      break;

    case PATTERN_CHASE:
      memset(txPacket + 1, 0, txSlots);
      txPacket[1 + (phase % max<uint16_t>(txSlots, 1))] = 255;
      phase++;
      break;

    case PATTERN_BLINK:
      memset(txPacket + 1, blinkOn ? 255 : 0, txSlots);
      blinkOn = !blinkOn;
      break;
  }
}

static void sendDmxFrame() {
  updateTxPattern();

  Serial1.flush();
  Serial1.end();

  pinMode(DMX_TX_PIN, OUTPUT);
  digitalWrite(DMX_TX_PIN, LOW);
  delayMicroseconds(txBreakUs);
  digitalWrite(DMX_TX_PIN, HIGH);
  delayMicroseconds(txMabUs);

  Serial1.setTX(DMX_TX_PIN);
  Serial1.begin(txBaud, SERIAL_8N2);

  if (txInterSlotUs == 0) {
    Serial1.write(txPacket, txSlots + 1);
  } else {
    for (uint16_t i = 0; i <= txSlots; i++) {
      Serial1.write(txPacket[i]);
      Serial1.flush();

      if (i < txSlots) {
        delayMicroseconds(txInterSlotUs);
      }
    }
  }

  Serial1.flush();

  if (txMbbUs > 0) {
    delayMicroseconds(txMbbUs);
  }

  txFrames++;
}

static void pollTx() {
  if (!txEnabled || mode != MODE_TX) {
    return;
  }

  const uint32_t now = millis();

  if ((int32_t)(now - nextTxMs) < 0) {
    return;
  }

  sendDmxFrame();

  const uint32_t periodMs =
    txFps == 0 ? 0 : max<uint32_t>(1, 1000 / txFps);
  nextTxMs =
    periodMs == 0 ? now : now + periodMs;
}

static void printStatsLine(
  const char* label,
  const RunningStats& values,
  const char* unit) {
  Serial.printf(
    "%-12s min=%8lu%s avg=%8.1f%s max=%8lu%s n=%lu\r\n",
    label,
    values.minOrZero(),
    unit,
    values.average(),
    unit,
    values.maxValue,
    unit,
    values.count);
}

static void printAnalyzerStats() {
  Serial.println();
  Serial.println(F("Analyzer statistics"));
  Serial.println(F("-------------------"));
  Serial.printf("Frames      : %lu\r\n", stats.frames);
  Serial.printf("FPS         : %.2f\r\n", stats.fps);
  Serial.printf("Short frames: %lu\r\n", stats.shortFrames);
  Serial.printf("Start code  : 0x%02X\r\n", lastFrame.startCode);
  Serial.printf("Last slots  : %u\r\n", lastFrame.slots);
  printStatsLine("Break", stats.breakUs, "us");
  printStatsLine("MAB", stats.mabUs, "us");
  printStatsLine("Frame", stats.frameToFrameUs, "us");
  printStatsLine("Data", stats.dataUs, "us");
  printStatsLine("Slots", stats.slots, "");

  if (lastFrame.dataUs > 0 && lastFrame.slots > 0) {
    const float estimatedBaud =
      (lastFrame.slots + 1) * 11.0f * 1000000.0f /
      lastFrame.dataUs;
    Serial.printf("Baud est.   : %.0f Bd (rough, USB-loop timestamp based)\r\n",
                  estimatedBaud);
  }
}

static void printTxStatus() {
  Serial.println();
  Serial.println(F("TX sender"));
  Serial.println(F("---------"));
  Serial.printf("Enabled : %s\r\n", txEnabled ? "yes" : "no");
  Serial.printf("Slots   : %u data slots + start code\r\n", txSlots);
  Serial.printf("Break   : %lu us\r\n", txBreakUs);
  Serial.printf("MAB     : %lu us\r\n", txMabUs);
  Serial.printf("MBB     : %lu us\r\n", txMbbUs);
  Serial.printf("Inter   : %lu us\r\n", txInterSlotUs);
  Serial.printf("Baud    : %lu Bd\r\n", txBaud);
  Serial.printf("FPS     : %lu\r\n", txFps);
  Serial.printf("Pattern : %s\r\n", patternName());
  Serial.printf("Frames  : %lu\r\n", txFrames);
}

static void printChannelTable() {
  Serial.print(F("\033[H"));
  Serial.printf("RP2040 DMX Tool | %s | ", modeName());

  if (mode == MODE_RX) {
    Serial.printf(
      "FPS %5.2f | slots %3u | break %4lu us | MAB %3lu us | start 0x%02X | view %u-%u\r\n\r\n",
      stats.fps,
      lastFrame.slots,
      lastFrame.breakUs,
      lastFrame.mabUs,
      lastFrame.startCode,
      displayFirstChannel,
      displayFirstChannel + displayChannelCount - 1);
  } else if (mode == MODE_TX) {
    Serial.printf(
      "TX %s | slots %3u | break %4lu us | MAB %3lu us | %lu fps | view %u-%u\r\n\r\n",
      txEnabled ? "on " : "off",
      txSlots,
      txBreakUs,
      txMabUs,
      txFps,
      displayFirstChannel,
      displayFirstChannel + displayChannelCount - 1);
  } else {
    Serial.println(F("idle\r\n"));
  }

  Serial.println(F("      00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F"));
  Serial.println();

  const uint32_t now = millis();
  const uint16_t firstIndex =
    displayFirstChannel - 1;
  const uint16_t count =
    min<uint16_t>(
      displayChannelCount,
      DMX_MAX_SLOTS - firstIndex);
  const uint16_t rows =
    (count + 15) / 16;

  for (uint16_t row = 0; row < rows; row++) {
    const uint16_t rowFirst =
      firstIndex + row * 16;

    Serial.printf("%04u: ", rowFirst + 1);

    for (uint16_t col = 0; col < 16; col++) {
      const uint16_t offset =
        row * 16 + col;

      if (offset >= count) {
        Serial.print(F("   "));
        continue;
      }

      const uint16_t ch =
        rowFirst + col;
      const uint8_t value =
        mode == MODE_TX
          ? txPacket[ch + 1]
          : rxValues[ch];

      const bool changed =
        mode == MODE_RX
        && now - rxChangeMs[ch] < CHANGE_HIGHLIGHT_MS;

      if (changed && colorEnabled) {
        Serial.print(F("\033[31m"));
      }

      Serial.printf("%02X", value);

      if (changed && colorEnabled) {
        Serial.print(F("\033[0m"));
      }

      Serial.print(' ');
    }

    Serial.println();
  }

  Serial.println();
  Serial.println(F("Commands: help | rx | tx | start | stop | set <ch> <0-255> | slots <0-512> | window <first> <count> | stats"));
}

static void maybeDrawDisplay() {
  if (!displayEnabled) {
    return;
  }

  const uint32_t now = millis();

  if (!dirtyDisplay && now < nextDisplayMs) {
    return;
  }

  dirtyDisplay = false;
  nextDisplayMs = now + DISPLAY_INTERVAL_MS;
  printChannelTable();
}

static bool parseNumber(
  const String& text,
  uint32_t& value) {
  if (text.length() == 0) {
    return false;
  }

  char* end = nullptr;
  value = strtoul(text.c_str(), &end, 0);
  return end != text.c_str() && *end == '\0';
}

static String nextToken(
  String& line) {
  line.trim();

  const int space = line.indexOf(' ');

  if (space < 0) {
    const String token = line;
    line = "";
    return token;
  }

  const String token = line.substring(0, space);
  line = line.substring(space + 1);
  return token;
}

static void setAllChannels(
  uint8_t value) {
  memset(txPacket + 1, value, DMX_MAX_SLOTS);
  pattern = PATTERN_STATIC;
  dirtyDisplay = true;
}

static void setDisplayWindow(
  uint16_t firstChannel,
  uint16_t channelCount) {
  displayFirstChannel =
    clampU32(
      firstChannel,
      1,
      DMX_MAX_SLOTS);

  displayChannelCount =
    clampU32(
      channelCount,
      1,
      DMX_MAX_SLOTS - displayFirstChannel + 1);

  dirtyDisplay = true;
}

static void setSingleChannel(
  uint16_t channel,
  uint8_t value) {
  if (channel < 1 || channel > DMX_MAX_SLOTS) {
    Serial.println(F("ERR channel must be 1..512"));
    return;
  }

  txPacket[channel] = value;
  pattern = PATTERN_STATIC;
  dirtyDisplay = true;
}

static void enterRxMode(bool printLegacy) {
  mode = MODE_RX;
  txEnabled = false;
  configureDmxSerialForRx();
  stats.reset();
  rxReceiving = false;
  rxPacketBytes = 0;
  if (printLegacy) {
    Serial.println(F("OK mode=rx"));
  }
  dirtyDisplay = true;
}

static void enterTxMode(bool printLegacy) {
  mode = MODE_TX;
  configureDmxSerialForTx();
  nextTxMs = millis();
  if (printLegacy) {
    Serial.println(F("OK mode=tx"));
  }
  dirtyDisplay = true;
}

static void enterIdleMode(bool printLegacy) {
  txEnabled = false;
  mode = MODE_IDLE;
  detachInterrupt(digitalPinToInterrupt(DMX_RX_PIN));
  Serial1.end();
  setDirectionPin(false);
  if (printLegacy) {
    Serial.println(F("OK mode=idle"));
  }
  dirtyDisplay = true;
}

static void writeJsonLine(
  JsonDocument& doc) {
  serializeJson(doc, Serial);
  Serial.println();
}

static void sendJsonOk(
  const char* type) {
  JsonDocument doc;
  doc["ok"] = true;
  doc["type"] = type;
  writeJsonLine(doc);
}

static void sendJsonError(
  const char* error,
  const char* message) {
  JsonDocument doc;
  doc["ok"] = false;
  doc["error"] = error;
  doc["message"] = message;
  writeJsonLine(doc);
}

static void sendJsonReady() {
  JsonDocument doc;
  doc["ok"] = true;
  doc["event"] = "ready";
  doc["tool"] = "rp2040_dmx_tool";
  doc["fw"] = TOOL_VERSION;
  doc["protocol"] = "jsonl";
  writeJsonLine(doc);
}

static void addRunningStatsJson(
  JsonObject target,
  const RunningStats& values,
  const char* unit) {
  target["min"] = values.minOrZero();
  target["avg"] = values.average();
  target["max"] = values.count ? values.maxValue : 0;
  target["n"] = values.count;
  target["unit"] = unit;
}

static void sendStatsJson() {
  JsonDocument doc;
  doc["ok"] = true;
  doc["type"] = "stats";
  doc["mode"] = modeName();

  if (mode == MODE_TX) {
    doc["txEnabled"] = txEnabled;
    doc["frames"] = txFrames;
    doc["slots"] = txSlots;
    doc["breakUs"] = txBreakUs;
    doc["mabUs"] = txMabUs;
    doc["mbbUs"] = txMbbUs;
    doc["interSlotUs"] = txInterSlotUs;
    doc["baud"] = txBaud;
    doc["fps"] = txFps;
    doc["pattern"] = patternName();
  } else {
    doc["frames"] = stats.frames;
    doc["fps"] = stats.fps;
    doc["shortFrames"] = stats.shortFrames;
    doc["longFrames"] = stats.longFrames;
    doc["framingBreaks"] = stats.framingBreaks;
    doc["startCode"] = lastFrame.startCode;
    doc["lastSlots"] = lastFrame.slots;
    doc["lastBreakUs"] = lastFrame.breakUs;
    doc["lastMabUs"] = lastFrame.mabUs;
    doc["lastFrameToFrameUs"] = lastFrame.frameToFrameUs;
    doc["lastDataUs"] = lastFrame.dataUs;
    if (lastFrame.dataUs > 0 && lastFrame.slots > 0) {
      doc["baudEstimate"] =
        (lastFrame.slots + 1) * 11.0f * 1000000.0f /
        lastFrame.dataUs;
    } else {
      doc["baudEstimate"] = 0;
    }

    addRunningStatsJson(doc["breakUs"].to<JsonObject>(), stats.breakUs, "us");
    addRunningStatsJson(doc["mabUs"].to<JsonObject>(), stats.mabUs, "us");
    addRunningStatsJson(doc["frameUs"].to<JsonObject>(), stats.frameToFrameUs, "us");
    addRunningStatsJson(doc["dataUs"].to<JsonObject>(), stats.dataUs, "us");
    addRunningStatsJson(doc["slots"].to<JsonObject>(), stats.slots, "");
  }

  writeJsonLine(doc);
}

static uint8_t frameValueAt(
  uint16_t channel) {
  if (channel < 1 || channel > DMX_MAX_SLOTS) {
    return 0;
  }

  return mode == MODE_TX
    ? txPacket[channel]
    : rxValues[channel - 1];
}

static void sendFrameJson(
  uint16_t firstChannel,
  uint16_t channelCount) {
  firstChannel =
    clampU32(
      firstChannel,
      1,
      DMX_MAX_SLOTS);
  channelCount =
    clampU32(
      channelCount,
      1,
      DMX_MAX_SLOTS - firstChannel + 1);

  Serial.print(F("{\"ok\":true,\"type\":\"frame\",\"mode\":\""));
  Serial.print(modeName());
  Serial.print(F("\",\"seq\":"));
  Serial.print(stats.frames);
  Serial.print(F(",\"startCode\":"));
  Serial.print(mode == MODE_TX ? txPacket[0] : lastFrame.startCode);
  Serial.print(F(",\"slots\":"));
  Serial.print(mode == MODE_TX ? txSlots : lastFrame.slots);
  Serial.print(F(",\"start\":"));
  Serial.print(firstChannel);
  Serial.print(F(",\"count\":"));
  Serial.print(channelCount);
  Serial.print(F(",\"values\":["));

  for (uint16_t i = 0; i < channelCount; i++) {
    if (i > 0) {
      Serial.print(',');
    }
    Serial.print(frameValueAt(firstChannel + i));
  }

  Serial.println(F("]}"));
}

static bool setPatternByName(
  const char* name) {
  if (!name) {
    return false;
  }

  String arg = name;
  arg.toLowerCase();

  if (arg == "static") {
    pattern = PATTERN_STATIC;
  } else if (arg == "ramp") {
    pattern = PATTERN_RAMP;
  } else if (arg == "chase") {
    pattern = PATTERN_CHASE;
  } else if (arg == "blink") {
    pattern = PATTERN_BLINK;
  } else {
    return false;
  }

  dirtyDisplay = true;
  return true;
}

static void handleJsonMode(
  JsonDocument& doc) {
  const char* value = doc["value"] | "";
  String target = value;
  target.toLowerCase();

  if (target == "rx") {
    enterRxMode(false);
  } else if (target == "tx") {
    enterTxMode(false);
  } else if (target == "idle") {
    enterIdleMode(false);
  } else {
    sendJsonError("invalid_mode", "Mode must be rx, tx, or idle");
    return;
  }

  JsonDocument reply;
  reply["ok"] = true;
  reply["type"] = "mode";
  reply["mode"] = modeName();
  writeJsonLine(reply);
}

static void handleJsonGet(
  JsonDocument& doc) {
  const char* target = doc["target"] | "";
  String targetText = target;
  targetText.toLowerCase();

  if (targetText == "stats") {
    sendStatsJson();
  } else if (targetText == "frame" || targetText == "channels") {
    const uint16_t start =
      clampU32(doc["start"] | 1, 1, DMX_MAX_SLOTS);
    const uint16_t defaultCount =
      targetText == "frame"
        ? min<uint16_t>(
            mode == MODE_TX ? txSlots : lastFrame.slots,
            DMX_MAX_SLOTS - start + 1)
        : 16;
    const uint16_t count =
      clampU32(doc["count"] | defaultCount, 1, DMX_MAX_SLOTS - start + 1);
    sendFrameJson(start, count);
  } else {
    sendJsonError("invalid_target", "Get target must be stats, frame, or channels");
  }
}

static void handleJsonSet(
  JsonDocument& doc) {
  const char* target = doc["target"] | "";
  String targetText = target;
  targetText.toLowerCase();

  if (targetText == "slots") {
    txSlots = clampU32(doc["value"] | txSlots, 0, DMX_MAX_SLOTS);
    sendJsonOk("slots");
  } else if (targetText == "timing") {
    txBreakUs = clampU32(doc["breakUs"] | txBreakUs, 44, 1000000);
    txMabUs = clampU32(doc["mabUs"] | txMabUs, 0, 1000000);
    txMbbUs = clampU32(doc["mbbUs"] | txMbbUs, 0, 1000000);
    txInterSlotUs = clampU32(doc["interSlotUs"] | txInterSlotUs, 0, 1000000);
    txBaud = clampU32(doc["baud"] | txBaud, 200000, 300000);
    txFps = clampU32(doc["fps"] | txFps, 0, 1000);
    if (mode == MODE_TX) {
      configureDmxSerialForTx();
    }
    sendJsonOk("timing");
  } else if (targetText == "channel") {
    const uint16_t channel = doc["channel"] | 0;
    const uint8_t value = clampU32(doc["value"] | 0, 0, 255);
    if (channel < 1 || channel > DMX_MAX_SLOTS) {
      sendJsonError("invalid_channel", "Channel must be 1..512");
      return;
    }
    txPacket[channel] = value;
    pattern = PATTERN_STATIC;
    sendJsonOk("channel");
  } else if (targetText == "channels") {
    JsonObject values = doc["values"].as<JsonObject>();
    if (values.isNull()) {
      sendJsonError("invalid_values", "values must be an object of channel:value pairs");
      return;
    }

    for (JsonPair pair : values) {
      const uint16_t channel =
        static_cast<uint16_t>(strtoul(pair.key().c_str(), nullptr, 10));
      if (channel < 1 || channel > DMX_MAX_SLOTS) {
        sendJsonError("invalid_channel", "Channel keys must be 1..512");
        return;
      }
      txPacket[channel] = clampU32(pair.value().as<uint32_t>(), 0, 255);
    }
    pattern = PATTERN_STATIC;
    sendJsonOk("channels");
  } else if (targetText == "frame") {
    JsonArray values = doc["values"].as<JsonArray>();
    if (values.isNull()) {
      sendJsonError("invalid_values", "values must be an array");
      return;
    }

    txPacket[0] = clampU32(doc["startCode"] | 0, 0, 255);
    txSlots = clampU32(doc["slots"] | values.size(), 0, DMX_MAX_SLOTS);
    memset(txPacket + 1, 0, DMX_MAX_SLOTS);

    uint16_t channel = 1;
    for (JsonVariant value : values) {
      if (channel > DMX_MAX_SLOTS) {
        break;
      }
      txPacket[channel++] = clampU32(value.as<uint32_t>(), 0, 255);
    }

    pattern = PATTERN_STATIC;
    sendJsonOk("frame");
  } else if (targetText == "pattern") {
    if (!setPatternByName(doc["value"] | "")) {
      sendJsonError("invalid_pattern", "Pattern must be static, ramp, chase, or blink");
      return;
    }
    sendJsonOk("pattern");
  } else {
    sendJsonError("invalid_target", "Unsupported set target");
  }
}

static void handleJsonTx(
  JsonDocument& doc) {
  const char* action = doc["action"] | "";
  String actionText = action;
  actionText.toLowerCase();

  if (actionText == "start") {
    enterTxMode(false);
    txEnabled = true;
    nextTxMs = millis();
    sendJsonOk("tx");
  } else if (actionText == "stop") {
    txEnabled = false;
    sendJsonOk("tx");
  } else if (actionText == "send") {
    enterTxMode(false);
    sendDmxFrame();
    sendJsonOk("tx");
  } else {
    sendJsonError("invalid_action", "TX action must be start, stop, or send");
  }
}

static void processJsonCommand(
  const String& line) {
  JsonDocument doc;
  DeserializationError error =
    deserializeJson(doc, line);

  if (error) {
    sendJsonError("json_parse_error", error.c_str());
    return;
  }

  const char* command = doc["cmd"] | "";
  String commandText = command;
  commandText.toLowerCase();

  if (commandText == "ping") {
    JsonDocument reply;
    reply["ok"] = true;
    reply["type"] = "pong";
    reply["fw"] = TOOL_VERSION;
    reply["mode"] = modeName();
    writeJsonLine(reply);
  } else if (commandText == "mode") {
    handleJsonMode(doc);
  } else if (commandText == "get") {
    handleJsonGet(doc);
  } else if (commandText == "set") {
    handleJsonSet(doc);
  } else if (commandText == "tx") {
    handleJsonTx(doc);
  } else if (commandText == "clear") {
    const char* target = doc["target"] | "";
    if (String(target) == "stats") {
      stats.reset();
      txFrames = 0;
      sendJsonOk("clear");
    } else {
      sendJsonError("invalid_target", "Clear target must be stats");
    }
  } else if (commandText == "help") {
    JsonDocument reply;
    reply["ok"] = true;
    reply["type"] = "help";
    JsonArray commands = reply["commands"].to<JsonArray>();
    commands.add("{\"cmd\":\"ping\"}");
    commands.add("{\"cmd\":\"mode\",\"value\":\"rx|tx|idle\"}");
    commands.add("{\"cmd\":\"get\",\"target\":\"stats\"}");
    commands.add("{\"cmd\":\"get\",\"target\":\"frame\",\"start\":1,\"count\":16}");
    commands.add("{\"cmd\":\"set\",\"target\":\"frame\",\"slots\":6,\"values\":[0,1,2]}");
    commands.add("{\"cmd\":\"set\",\"target\":\"channels\",\"values\":{\"1\":255}}");
    commands.add("{\"cmd\":\"set\",\"target\":\"timing\",\"breakUs\":176,\"mabUs\":16}");
    commands.add("{\"cmd\":\"tx\",\"action\":\"start|stop|send\"}");
    writeJsonLine(reply);
  } else {
    sendJsonError("unknown_command", "Unknown JSON command");
  }
}

static void processCommand(
  String line) {
  line.trim();

  if (line.length() == 0) {
    return;
  }

  if (line[0] == '{') {
    processJsonCommand(line);
    return;
  }

  String command = nextToken(line);
  command.toLowerCase();

  if (command == "help" || command == "?") {
    printHelp();
  } else if (command == "rx") {
    enterRxMode();
  } else if (command == "tx") {
    enterTxMode();
  } else if (command == "idle") {
    enterIdleMode();
  } else if (command == "start") {
    enterTxMode();
    txEnabled = true;
    nextTxMs = millis();
    Serial.println(F("OK tx started"));
  } else if (command == "stop") {
    txEnabled = false;
    Serial.println(F("OK tx stopped"));
  } else if (command == "stats") {
    if (mode == MODE_TX) {
      printTxStatus();
    } else {
      printAnalyzerStats();
    }
  } else if (command == "clear") {
    Serial.print(F("\033[2J\033[H"));
    dirtyDisplay = true;
  } else if (command == "reset") {
    stats.reset();
    txFrames = 0;
    Serial.println(F("OK counters reset"));
  } else if (command == "view") {
    String arg = nextToken(line);
    arg.toLowerCase();
    displayEnabled = arg != "off";
    Serial.println(displayEnabled ? F("OK view on") : F("OK view off"));
  } else if (command == "color") {
    String arg = nextToken(line);
    arg.toLowerCase();
    colorEnabled = arg != "off";
    Serial.println(colorEnabled ? F("OK color on") : F("OK color off"));
  } else if (command == "window") {
    uint32_t firstChannel;
    uint32_t channelCount;

    if (parseNumber(nextToken(line), firstChannel)
        && parseNumber(nextToken(line), channelCount)) {
      setDisplayWindow(firstChannel, channelCount);
      Serial.printf(
        "OK window=%u-%u\r\n",
        displayFirstChannel,
        displayFirstChannel + displayChannelCount - 1);
    } else {
      Serial.println(F("ERR usage: window <first channel> <count>"));
    }
  } else if (command == "slots") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txSlots = clampU32(value, 0, DMX_MAX_SLOTS);
      Serial.printf("OK slots=%u\r\n", txSlots);
      dirtyDisplay = true;
    }
  } else if (command == "break") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txBreakUs = clampU32(value, 44, 1000000);
      Serial.printf("OK break=%luus\r\n", txBreakUs);
    }
  } else if (command == "mab") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txMabUs = clampU32(value, 0, 1000000);
      Serial.printf("OK mab=%luus\r\n", txMabUs);
    }
  } else if (command == "mbb") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txMbbUs = clampU32(value, 0, 1000000);
      Serial.printf("OK mbb=%luus\r\n", txMbbUs);
    }
  } else if (command == "inter") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txInterSlotUs = clampU32(value, 0, 1000000);
      Serial.printf("OK inter=%luus\r\n", txInterSlotUs);
    }
  } else if (command == "baud") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txBaud = clampU32(value, 200000, 300000);
      Serial.printf("OK baud=%lu\r\n", txBaud);
      if (mode == MODE_TX) {
        configureDmxSerialForTx();
      }
    }
  } else if (command == "fps") {
    uint32_t value;
    if (parseNumber(nextToken(line), value)) {
      txFps = clampU32(value, 0, 1000);
      Serial.printf("OK fps=%lu\r\n", txFps);
    }
  } else if (command == "set") {
    uint32_t channel;
    uint32_t value;

    if (parseNumber(nextToken(line), channel)
        && parseNumber(nextToken(line), value)) {
      setSingleChannel(channel, clampU32(value, 0, 255));
      Serial.printf("OK ch%lu=%lu\r\n", channel, clampU32(value, 0, 255));
    } else {
      Serial.println(F("ERR usage: set <channel 1..512> <value 0..255>"));
    }
  } else if (command == "all") {
    uint32_t value;

    if (parseNumber(nextToken(line), value)) {
      setAllChannels(clampU32(value, 0, 255));
      Serial.printf("OK all=%lu\r\n", clampU32(value, 0, 255));
    }
  } else if (command == "pattern") {
    String arg = nextToken(line);
    arg.toLowerCase();

    if (arg == "static") {
      pattern = PATTERN_STATIC;
    } else if (arg == "ramp") {
      pattern = PATTERN_RAMP;
    } else if (arg == "chase") {
      pattern = PATTERN_CHASE;
    } else if (arg == "blink") {
      pattern = PATTERN_BLINK;
    } else {
      Serial.println(F("ERR pattern: static|ramp|chase|blink"));
      return;
    }

    Serial.printf("OK pattern=%s\r\n", patternName());
    dirtyDisplay = true;
  } else if (command == "send") {
    enterTxMode();
    sendDmxFrame();
    Serial.println(F("OK one frame sent"));
  } else {
    Serial.println(F("ERR unknown command; type help"));
  }
}

static void pollUsbCommands() {
  while (Serial.available() > 0) {
    const char c =
      static_cast<char>(Serial.read());

    if (c == '\r' || c == '\n') {
      processCommand(commandLine);
      commandLine = "";
    } else if (c == '\b' || c == 0x7F) {
      if (commandLine.length() > 0) {
        commandLine.remove(commandLine.length() - 1);
      }
    } else if (isPrintable(c)) {
      if (commandLine.length() < MAX_COMMAND_LINE_LENGTH) {
        commandLine += c;
      } else {
        commandLine = "";
        sendJsonError("line_too_long", "Command line exceeds maximum length");
      }
    }
  }
}

static void printHelp() {
  Serial.println();
  Serial.println(F("RP2040 DMX Analyzer / Test Sender"));
  Serial.println(F("----------------------------------"));
  Serial.println(F("Modes"));
  Serial.println(F("  rx                  Analyzer mode"));
  Serial.println(F("  tx                  Sender mode without starting continuous output"));
  Serial.println(F("  idle                Stop RX/TX"));
  Serial.println(F("  start               Start continuous DMX output"));
  Serial.println(F("  stop                Stop continuous DMX output"));
  Serial.println();
  Serial.println(F("Analyzer"));
  Serial.println(F("  stats               Show frame, FPS, slot, Break and MAB statistics"));
  Serial.println(F("  reset               Reset counters/statistics"));
  Serial.println(F("  view on|off         Toggle live ASCII channel table"));
  Serial.println(F("  color on|off        Toggle ANSI highlight colors"));
  Serial.println(F("  window <first> <n>  Live table window, default 1 64"));
  Serial.println(F("                      Use view off for the cleanest statistics"));
  Serial.println();
  Serial.println(F("Sender"));
  Serial.println(F("  slots <0..512>      Number of data slots after start code"));
  Serial.println(F("  set <ch> <value>    Set one channel, 1-based"));
  Serial.println(F("  all <value>         Set all 512 channel values"));
  Serial.println(F("  pattern static|ramp|chase|blink"));
  Serial.println(F("  break <us>          Break duration"));
  Serial.println(F("  mab <us>            Mark-after-break duration"));
  Serial.println(F("  mbb <us>            Extra mark-before-break / inter-packet gap"));
  Serial.println(F("  inter <us>          Extra mark time between transmitted slots"));
  Serial.println(F("  baud <baud>         Slot baudrate, default 250000"));
  Serial.println(F("  fps <hz>            Continuous sender rate"));
  Serial.println(F("  send                Send exactly one frame"));
  Serial.println();
  Serial.println(F("DMX512-A baseline: 250 kBd 8N2, transmitter Break >=92 us,"));
  Serial.println(F("MAB >=12 us. Receivers should recognize Break >=88 us and MAB >=8 us."));
  Serial.println(F("Short packets are valid; up to 512 data slots may follow start code 0x00."));
}

void setup() {
  Serial.begin(115200);
  delay(1200);

  memset(rxPacket, 0, sizeof(rxPacket));
  memset(rxValues, 0, sizeof(rxValues));
  memset(previousRxValues, 0, sizeof(previousRxValues));
  memset(rxChangeMs, 0, sizeof(rxChangeMs));
  memset(txPacket, 0, sizeof(txPacket));

  stats.reset();

  enterRxMode(false);
  sendJsonReady();
}

void loop() {
  pollUsbCommands();

  if (mode == MODE_RX) {
    pollDmxRxEdges();
    pollDmxRxBytes();
    updateRxFps();
  }

  pollTx();
  maybeDrawDisplay();
}
