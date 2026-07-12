#pragma once

// Unique entry point for the uNode-maintained fork. Keeping the original
// implementation header behind this wrapper preserves API compatibility while
// preventing Arduino from selecting a globally installed upstream library.
#include "LXESP8266UARTDMX.h"
