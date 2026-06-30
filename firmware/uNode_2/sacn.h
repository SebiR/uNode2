#pragma once

#include <Arduino.h>

/** @brief Initializes the sACN E1.31 UDP socket and multicast membership. */
bool initSacn();
/** @brief Processes incoming sACN packets and timeout handling. */
void updateSacn();
/** @brief Rebinds sACN after the active network interface changes. */
void handleSacnNetworkChange();

/** @return Configured sACN Universe, clamped away from the invalid Universe 0. */
uint16_t getSacnUniverse();

/** @return True when the sACN socket is ready. */
bool isSacnSocketReady();
/** @return True while recent sACN data is driving DMX output. */
bool isSacnActive();
/** @return True after sACN timeout has applied output failsafe. */
bool isSacnFailsafeActive();
/** @return Number of accepted sACN data packets. */
uint32_t getSacnPacketCount();
/** @return Number of UDP packets received on the sACN socket. */
uint32_t getSacnUdpPacketCount();
/** @return Accepted sACN data packets during the previous second. */
uint32_t getSacnFPS();
/** @return Milliseconds since the last accepted sACN packet, or zero. */
uint32_t getLastSacnPacketAge();
/** @return Number of sACN packets ignored because they target another Universe. */
uint32_t getSacnWrongUniverseCount();
/** @return Last wrong sACN Universe seen by the node. */
uint16_t getSacnLastWrongUniverse();
/** @return Number of malformed or unsupported sACN packets. */
uint32_t getSacnMalformedPacketCount();
/** @return Number of sACN packets dropped by sequence tracking. */
uint32_t getSacnSequenceDropCount();
/** @return Number of valid sACN packets ignored because sACN live mode is off. */
uint32_t getSacnProtocolDropCount();
/** @return Number of valid sACN packets ignored because direction is DMX input. */
uint32_t getSacnDirectionDropCount();
/** @return Number of sACN lower-priority packets ignored. */
uint32_t getSacnPriorityDropCount();
/** @return Number of stream-terminated packets accepted. */
uint32_t getSacnStreamTerminatedCount();
/** @return Number of sACN sources currently considered alive. */
uint8_t getSacnActiveSourceCount();
/** @return Priority of the currently winning source, or zero when idle. */
uint8_t getSacnWinningPriority();
/** @return Number of sACN source-loss timeouts. */
uint32_t getSacnSourceTimeoutCount();

/** @return True when the current frame was sent as sACN multicast. */
bool sendSacnFrame();
