#pragma once

#include <Arduino.h>

struct EventLogEntry {
  uint32_t uptimeMillis;
  char key[28];
  char message[112];
  uint16_t repeats;
};

void logEvent(
  const char* key,
  const char* message,
  uint32_t throttleMillis = 10000);

uint8_t getEventLogCount();

bool getEventLogEntry(
  uint8_t index,
  EventLogEntry& entry);

void clearEventLog();
