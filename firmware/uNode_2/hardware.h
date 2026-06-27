#pragma once

#include "config.h"

/** @brief Initializes board-level GPIOs that are not owned by protocol drivers. */
void initHardware();

/** @brief Applies the configured RS-485 transceiver direction and termination. */
void applyHardwareForDirection();

/** @brief Applies only the configured termination mode. */
void applyTermination();

/** @return True when this build controls separate RS-485 /RE and DE pins. */
bool isRs485SplitControlSupported();

/** @return True when this build controls the DMX bus termination switch. */
bool isTerminationControlSupported();

/** @return True when the RS-485 driver output is currently enabled. */
bool isRs485DriverEnabled();

/** @return True when the RS-485 receiver input is currently enabled. */
bool isRs485ReceiverEnabled();

/** @return True when switchable bus termination is currently enabled. */
bool isTerminationEnabled();

