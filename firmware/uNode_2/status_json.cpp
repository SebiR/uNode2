#include "status_json.h"

#include "artnet.h"

/** @return Discovered Art-Net node name or the sender IP as fallback. */
static String getKnownArtNetName(
  const IPAddress& ip) {
  ArtNetSubscriberInfo subscriber;

  for (uint8_t i = 0;
       i < getArtNetSubscriberCount();
       i++) {
    if (!getArtNetSubscriber(i, subscriber)) {
      continue;
    }

    if (subscriber.ip == ip
        && subscriber.name[0] != '\0') {
      return String(subscriber.name);
    }
  }

  return ip.toString();
}

void addArtNetSourcesToJson(
  JsonDocument& doc) {
  JsonArray sources =
    doc["artNetSources"].to<JsonArray>();

  for (uint8_t i = 0;
       i < getArtNetSourceCount();
       i++) {
    ArtNetSourceInfo source;

    if (!getArtNetSource(i, source)) {
      continue;
    }

    JsonObject item =
      sources.add<JsonObject>();
    item["ip"] =
      source.ip.toString();
    item["name"] =
      getKnownArtNetName(source.ip);
    item["physical"] =
      source.physical;
    item["lastSeenAge"] =
      millis() - source.lastSeenMillis;
    item["winning"] =
      source.winning;
  }
}
