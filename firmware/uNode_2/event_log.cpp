#include "event_log.h"

#include <string.h>

static const uint8_t EVENT_LOG_CAPACITY = 16;

static EventLogEntry entries[EVENT_LOG_CAPACITY];
static uint8_t nextEntry = 0;
static uint8_t entryCount = 0;

static int8_t findNewestEntryByKey(
  const char* key) {
  if (!key) {
    return -1;
  }

  for (uint8_t i = 0;
       i < entryCount;
       i++) {
    const uint8_t index =
      (nextEntry + EVENT_LOG_CAPACITY - 1 - i)
      % EVENT_LOG_CAPACITY;

    if (strncmp(
          entries[index].key,
          key,
          sizeof(entries[index].key)) == 0) {
      return index;
    }
  }

  return -1;
}

static void copyText(
  char* destination,
  size_t destinationSize,
  const char* source) {
  if (destinationSize == 0) {
    return;
  }

  if (!source) {
    source = "";
  }

  strncpy(
    destination,
    source,
    destinationSize - 1);
  destination[destinationSize - 1] = '\0';
}

void logEvent(
  const char* key,
  const char* message,
  uint32_t throttleMillis) {
  if (!key || !message) {
    return;
  }

  const uint32_t now =
    millis();

  const int8_t existingIndex =
    findNewestEntryByKey(key);

  if (existingIndex >= 0
      && throttleMillis > 0
      && now - entries[existingIndex].uptimeMillis
          < throttleMillis) {
    if (entries[existingIndex].repeats < UINT16_MAX) {
      entries[existingIndex].repeats++;
    }

    entries[existingIndex].uptimeMillis =
      now;

    return;
  }

  EventLogEntry& entry =
    entries[nextEntry];

  entry.uptimeMillis =
    now;
  entry.repeats = 0;

  copyText(
    entry.key,
    sizeof(entry.key),
    key);
  copyText(
    entry.message,
    sizeof(entry.message),
    message);

  nextEntry =
    (nextEntry + 1) % EVENT_LOG_CAPACITY;

  if (entryCount < EVENT_LOG_CAPACITY) {
    entryCount++;
  }
}

uint8_t getEventLogCount() {
  return entryCount;
}

bool getEventLogEntry(
  uint8_t index,
  EventLogEntry& entry) {
  if (index >= entryCount) {
    return false;
  }

  const uint8_t oldest =
    entryCount == EVENT_LOG_CAPACITY
      ? nextEntry
      : 0;

  const uint8_t physicalIndex =
    (oldest + index) % EVENT_LOG_CAPACITY;

  entry =
    entries[physicalIndex];

  return true;
}

void clearEventLog() {
  nextEntry = 0;
  entryCount = 0;
  memset(
    entries,
    0,
    sizeof(entries));
}
