#pragma once

#include <ArduinoJson.h>

/**
 * @brief Appends the active Art-Net merge sources to a status document.
 * @param doc Destination document that receives the artNetSources array.
 */
void addArtNetSourcesToJson(JsonDocument& doc);
