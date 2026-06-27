#pragma once

/** @brief Starts the status WebSocket server and registers event handling. */
bool initWebSocket();

/** @brief Processes clients and emits changed LED or status data. */
void updateWebSocket();

/** @brief Broadcasts a complete runtime status snapshot. */
void broadcastStatus();
