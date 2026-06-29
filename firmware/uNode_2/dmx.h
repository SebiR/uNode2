#pragma once

/** @brief Initializes UART DMX for the configured direction. */
bool initDMX();
/** @brief Optionally listens for external DMX at boot and switches to input. */
bool applyBootBusGuard();
/** @brief Stops and restarts UART DMX for the current configured direction. */
bool restartDMX();
/** @brief Processes pending frames, output updates, and activity metrics. */
void updateDMX();
/** @return Number of received physical DMX frames. */
uint32_t getDMXFrameCounter();
/** @return Physical DMX frames received during the previous second. */
uint32_t getDMXFPS();
/** @return Milliseconds since the last physical DMX frame, or zero. */
uint32_t getLastDMXFrameAge();
/** @return True while physical DMX input is considered active. */
bool isDMXActive();
