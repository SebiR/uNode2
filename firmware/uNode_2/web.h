#pragma once

/** @brief Registers HTTP routes and starts the web server. */
bool initWeb();

/** @brief Registers firmware-embedded recovery routes and starts the web server. */
bool initRecoveryWeb(bool filesystemMounted);

/** @brief Processes one iteration of HTTP client handling. */
void updateWeb();
