#include "PollReply.h"

static const uint16_t ARTNET_OEM_CODE = 0x3a28;
static const uint16_t ESTA_MANUFACTURER_CODE = 0x4173;

PollReply::PollReply()
  : startingUniverse(0),
    reportCode(RcPowerOk),
    reportCounter(0),
    legacyArtNet3Mode(false) {
  memset(&packet, 0, sizeof(packet));
  memset(reportText, 0, sizeof(reportText));

  const uint8_t id[8] = ARTNET_ID;
  memcpy(packet.ID, id, sizeof(packet.ID));

  packet.OpCodeLo = OpPollReply & 0xff;
  packet.OpCodeHi = OpPollReply >> 8;
  packet.PortLo = ARTNET_PORT & 0xff;
  packet.PortHi = ARTNET_PORT >> 8;
  packet.VersionInfoLo = 1;
  packet.OemHi = ARTNET_OEM_CODE >> 8;
  packet.OemLo = ARTNET_OEM_CODE & 0xff;
  packet.EstaManLo = ESTA_MANUFACTURER_CODE & 0xff;
  packet.EstaManHi = ESTA_MANUFACTURER_CODE >> 8;
  packet.BindIndex = 1;
  packet.Status2 = 0x08; // 15-bit Port-Address supported.
  packet.Status3 = 0x08; // Port direction is configurable.
  packet.RefreshRateLo = 44;

  setIndicatorState(ArtNetIndicatorState::NORMAL);
  packet.Status1 |= 0x20; // Port-Address configured by network/web UI.
  setShortName("uNode");
  setLongName("uNode Art-Net Node");
  setNodeReport(RcPowerOk, "uNode Ready");
  setStartingUniverse(0);
}

void PollReply::setMac(const byte mac[]) {
  if (mac) {
    memcpy(packet.Mac, mac, sizeof(packet.Mac));
  }
}

void PollReply::setIP(IPAddress ip) {
  for (uint8_t i = 0; i < 4; i++) {
    packet.IPAddr[i] = ip[i];
  }
}

void PollReply::setBindIP(IPAddress ip) {
  for (uint8_t i = 0; i < 4; i++) {
    packet.BindIp[i] = ip[i];
  }
}

void PollReply::setFirmwareVersion(uint8_t high, uint8_t low) {
  packet.VersionInfoHi = high;
  packet.VersionInfoLo = low;
}

void PollReply::setOemCode(uint16_t code) {
  packet.OemHi = code >> 8;
  packet.OemLo = code & 0xff;
}

void PollReply::setEstaManufacturerCode(uint16_t code) {
  packet.EstaManLo = code & 0xff;
  packet.EstaManHi = code >> 8;
}

/**
 * @brief Copies a null-terminated string into a cleared fixed-width Art-Net field.
 *
 * @param destination Destination character array.
 * @param capacity Size of the destination field in bytes.
 * @param source Source string, or `nullptr` to leave the field empty.
 */
static void copyArtNetString(
  char* destination,
  size_t capacity,
  const char* source) {
  if (!destination || capacity == 0) {
    return;
  }

  memset(destination, 0, capacity);

  if (source) {
    strncpy(destination, source, capacity - 1);
  }
}

void PollReply::setShortName(const char name[]) {
  copyArtNetString(packet.PortName, sizeof(packet.PortName), name);
}

void PollReply::setLongName(const char name[]) {
  copyArtNetString(packet.LongName, sizeof(packet.LongName), name);
}

void PollReply::setNodeReport(uint16_t code, const char* text) {
  reportCode = code;
  copyArtNetString(reportText, sizeof(reportText), text);
  formatNodeReport();
}

void PollReply::formatNodeReport() {
  snprintf(
    packet.NodeReport,
    sizeof(packet.NodeReport),
    "#%04X [%04u] %s",
    reportCode,
    reportCounter,
    reportText);
}

void PollReply::setNumPorts(uint8_t num) {
  packet.NumPortsHi = 0;
  packet.NumPortsLo = min(num, (uint8_t)4);
}

void PollReply::clearPorts() {
  memset(packet.PortTypes, 0, sizeof(packet.PortTypes));
  memset(packet.GoodInput, 0, sizeof(packet.GoodInput));
  memset(packet.GoodOutputA, 0, sizeof(packet.GoodOutputA));
  memset(packet.GoodOutputB, 0, sizeof(packet.GoodOutputB));
  memset(packet.SwIn, 0, sizeof(packet.SwIn));
  memset(packet.SwOut, 0, sizeof(packet.SwOut));
  setNumPorts(0);
}

void PollReply::setPortType(uint8_t port, uint8_t type) {
  if (port < 4) {
    packet.PortTypes[port] = type;
  }
}

void PollReply::setSwIn(uint8_t port, uint16_t portAddress) {
  if (port < 4 && portAddress <= 0x7fff) {
    packet.SwIn[port] = portAddress & 0x0f;
  }
}

void PollReply::setSwOut(uint8_t port, uint16_t portAddress) {
  if (port < 4 && portAddress <= 0x7fff) {
    packet.SwOut[port] = portAddress & 0x0f;
  }
}

void PollReply::setOutputEnabled(uint8_t port) {
  if (port >= 4) {
    return;
  }

  packet.PortTypes[port] |= 0x80;
  // RDM disabled, continuous output style, no discovery.
  packet.GoodOutputB[port] = 0xf0;
  setSwOut(port, startingUniverse + port);
}

void PollReply::setOutputDisabled(uint8_t port) {
  if (port >= 4) {
    return;
  }

  packet.PortTypes[port] &= ~0x80;
  packet.GoodOutputA[port] = 0;
  packet.GoodOutputB[port] = 0;
  packet.SwOut[port] = 0;
}

void PollReply::setInputEnabled(uint8_t port) {
  if (port >= 4) {
    return;
  }

  packet.PortTypes[port] |= 0x40;
  setSwIn(port, startingUniverse + port);
}

void PollReply::setInputDisabled(uint8_t port) {
  if (port >= 4) {
    return;
  }

  packet.PortTypes[port] &= ~0x40;
  packet.GoodInput[port] = 0;
  packet.SwIn[port] = 0;
}

void PollReply::setInputDataActive(uint8_t port, bool active) {
  if (port < 4) {
    if (active) packet.GoodInput[port] |= 0x80;
    else packet.GoodInput[port] &= ~0x80;
  }
}

void PollReply::setOutputDataActive(uint8_t port, bool active) {
  if (port < 4) {
    if (active) packet.GoodOutputA[port] |= 0x80;
    else packet.GoodOutputA[port] &= ~0x80;
  }
}

void PollReply::setOutputMergeStatus(
  uint8_t port,
  bool active,
  bool ltpMode) {
  if (port >= 4) {
    return;
  }

  if (active) {
    packet.GoodOutputA[port] |= 0x08;
  } else {
    packet.GoodOutputA[port] &= ~0x08;
  }

  if (ltpMode) {
    packet.GoodOutputA[port] |= 0x02;
  } else {
    packet.GoodOutputA[port] &= ~0x02;
  }
}

void PollReply::canDHCP(bool can) {
  if (can) packet.Status2 |= 0x04;
  else packet.Status2 &= ~0x04;
}

void PollReply::isDHCP(bool is) {
  if (is) packet.Status2 |= 0x02;
  else packet.Status2 &= ~0x02;
}

void PollReply::setWebConfig(bool enabled) {
  if (enabled) packet.Status2 |= 0x01;
  else packet.Status2 &= ~0x01;
}

void PollReply::setLegacyArtNet3Mode(
  bool enabled) {
  legacyArtNet3Mode = enabled;
}

void PollReply::applyLegacyArtNet3Profile() {
  memset(
    packet.GoodOutputB,
    0,
    sizeof(packet.GoodOutputB));

  packet.Status3 = 0;

  memset(
    packet.DefaultRespUID,
    0,
    sizeof(packet.DefaultRespUID));

  packet.UserHi = 0;
  packet.UserLo = 0;
  packet.RefreshRateHi = 0;
  packet.RefreshRateLo = 0;
  packet.BackgroundQueuePolicy = 0;

  memset(
    packet.Filler,
    0,
    sizeof(packet.Filler));
}

void PollReply::setFailsafeStatus(
  uint8_t mode,
  bool programmable) {
  packet.Status3 =
    (packet.Status3 & 0x1f)
    | ((mode & 0x03) << 6);

  if (programmable) {
    packet.Status3 |= 0x20;
  }
}

void PollReply::setIndicatorState(ArtNetIndicatorState state) {
  packet.Status1 =
    (packet.Status1 & 0x3f)
    | ((static_cast<uint8_t>(state) & 0x03) << 6);

  if (state == ArtNetIndicatorState::LOCATE) {
    packet.Status2 |= 0x20;
  } else {
    packet.Status2 &= ~0x20;
  }
}

ArtNetIndicatorState PollReply::getIndicatorState() const {
  return static_cast<ArtNetIndicatorState>(
    (packet.Status1 >> 6) & 0x03);
}

uint8_t PollReply::getBindIndex() const {
  return packet.BindIndex;
}

void PollReply::setSquawking(bool enabled) {
  setIndicatorState(
    enabled
      ? ArtNetIndicatorState::LOCATE
      : ArtNetIndicatorState::NORMAL);
}

bool PollReply::isSquawking() const {
  return (packet.Status2 & 0x20) != 0;
}

void PollReply::setStartingUniverse(uint16_t startUniverse) {
  startingUniverse = min(startUniverse, (uint16_t)0x7fff);
  packet.NetSwitch = (startingUniverse >> 8) & 0x7f;
  packet.SubSwitch = (startingUniverse >> 4) & 0x0f;
  updatePortAddresses();
}

uint16_t PollReply::getStartingUniverse() const {
  return startingUniverse;
}

void PollReply::updatePortAddresses() {
  for (uint8_t port = 0; port < 4; port++) {
    if (packet.PortTypes[port] & 0x40) {
      setSwIn(port, startingUniverse + port);
    }

    if (packet.PortTypes[port] & 0x80) {
      setSwOut(port, startingUniverse + port);
    }
  }
}

uint8_t* PollReply::printPacket() {
  reportCounter = (reportCounter + 1) % 10000;
  formatNodeReport();

  if (legacyArtNet3Mode) {
    applyLegacyArtNet3Profile();
  }

  return reinterpret_cast<uint8_t*>(&packet);
}

const uint8_t* PollReply::data() const {
  return reinterpret_cast<const uint8_t*>(&packet);
}

size_t PollReply::size() const {
  return sizeof(packet);
}
