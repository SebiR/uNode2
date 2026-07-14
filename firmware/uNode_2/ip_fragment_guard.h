#pragma once

#include <Arduino.h>

/** @return True because this build rejects IPv4 fragmentation globally. */
bool isIpFragmentGuardEnabled();

/** @return Number of incoming IPv4 fragments discarded since boot. */
uint32_t getDroppedIpv4FragmentCount();

/** @return Number of oversized outgoing IPv4 packets rejected since boot. */
uint32_t getRejectedIpv4FragmentedTxCount();
