#ifndef POLLREPLY_H
#define POLLREPLY_H

#include <Arduino.h>
#include <IPAddress.h>
#include <stddef.h>

#include "OpCodes.h"
#include "NodeReportCodes.h"
#include "StyleCodes.h"
#include "PriorityCodes.h"
#include "ProtocolSettings.h"

// Art-Net 4 ArtPollReply, revision 1.4dp. Multi-byte fields are represented
// as explicit bytes so the wire format is independent of CPU endianness.
struct __attribute__((packed)) replyPollPacket {
  uint8_t ID[8];                    // 0
  uint8_t OpCodeLo;                 // 8
  uint8_t OpCodeHi;                 // 9
  uint8_t IPAddr[4];                // 10
  uint8_t PortLo;                   // 14
  uint8_t PortHi;                   // 15
  uint8_t VersionInfoHi;            // 16
  uint8_t VersionInfoLo;            // 17
  uint8_t NetSwitch;                // 18
  uint8_t SubSwitch;                // 19
  uint8_t OemHi;                    // 20
  uint8_t OemLo;                    // 21
  uint8_t UbeaVersion;              // 22
  uint8_t Status1;                  // 23
  uint8_t EstaManLo;                // 24
  uint8_t EstaManHi;                // 25
  char PortName[18];                // 26
  char LongName[64];                // 44
  char NodeReport[64];              // 108
  uint8_t NumPortsHi;               // 172
  uint8_t NumPortsLo;               // 173
  uint8_t PortTypes[4];             // 174
  uint8_t GoodInput[4];             // 178
  uint8_t GoodOutputA[4];           // 182
  uint8_t SwIn[4];                  // 186
  uint8_t SwOut[4];                 // 190
  uint8_t AcnPriority;              // 194
  uint8_t SwMacro;                  // 195
  uint8_t SwRemote;                 // 196
  uint8_t Spare[3];                 // 197
  uint8_t Style;                    // 200
  uint8_t Mac[6];                   // 201
  uint8_t BindIp[4];                // 207
  uint8_t BindIndex;                // 211
  uint8_t Status2;                  // 212
  uint8_t GoodOutputB[4];           // 213
  uint8_t Status3;                  // 217
  uint8_t DefaultRespUID[6];        // 218
  uint8_t UserHi;                   // 224
  uint8_t UserLo;                   // 225
  uint8_t RefreshRateHi;            // 226
  uint8_t RefreshRateLo;            // 227
  uint8_t BackgroundQueuePolicy;    // 228
  uint8_t Filler[10];               // 229
};

static_assert(sizeof(replyPollPacket) == 239,
              "ArtPollReply must be 239 bytes");
static_assert(offsetof(replyPollPacket, PortName) == 26,
              "ArtPollReply PortName offset mismatch");
static_assert(offsetof(replyPollPacket, NodeReport) == 108,
              "ArtPollReply NodeReport offset mismatch");
static_assert(offsetof(replyPollPacket, PortTypes) == 174,
              "ArtPollReply PortTypes offset mismatch");
static_assert(offsetof(replyPollPacket, GoodInput) == 178,
              "ArtPollReply GoodInput offset mismatch");
static_assert(offsetof(replyPollPacket, GoodOutputA) == 182,
              "ArtPollReply GoodOutputA offset mismatch");
static_assert(offsetof(replyPollPacket, SwIn) == 186,
              "ArtPollReply SwIn offset mismatch");
static_assert(offsetof(replyPollPacket, SwOut) == 190,
              "ArtPollReply SwOut offset mismatch");
static_assert(offsetof(replyPollPacket, BindIp) == 207,
              "ArtPollReply BindIp offset mismatch");
static_assert(offsetof(replyPollPacket, Status2) == 212,
              "ArtPollReply Status2 offset mismatch");
static_assert(offsetof(replyPollPacket, GoodOutputB) == 213,
              "ArtPollReply GoodOutputB offset mismatch");
static_assert(offsetof(replyPollPacket, RefreshRateHi) == 226,
              "ArtPollReply RefreshRate offset mismatch");

enum class ArtNetIndicatorState : uint8_t {
  UNKNOWN = 0,
  LOCATE = 1,
  MUTE = 2,
  NORMAL = 3
};

class PollReply {
public:
  /** @brief Constructs a specification-compliant default ArtPollReply. */
  PollReply();

  /** @brief Sets the six-byte MAC address. */
  void setMac(const byte mac[]);
  /** @brief Sets the advertised node IP address. */
  void setIP(IPAddress ip);
  /** @brief Sets the advertised root binding IP address. */
  void setBindIP(IPAddress ip);
  /** @brief Sets the two-byte firmware version. */
  void setFirmwareVersion(uint8_t high, uint8_t low);
  /** @brief Sets the ESTA-assigned Art-Net OEM product code. */
  void setOemCode(uint16_t code);
  /** @brief Sets the ESTA manufacturer identifier. */
  void setEstaManufacturerCode(uint16_t code);
  /** @brief Sets the fixed-width Art-Net Port Name. */
  void setShortName(const char name[]);
  /** @brief Sets the fixed-width Art-Net Long Name. */
  void setLongName(const char name[]);
  /** @brief Sets the report code and text used in NodeReport. */
  void setNodeReport(uint16_t code, const char* text);

  /** @brief Sets the advertised number of ports, clamped to four. */
  void setNumPorts(uint8_t num);
  /** @brief Clears all port types, addresses, and activity flags. */
  void clearPorts();
  /** @brief Sets one raw PortTypes entry. */
  void setPortType(uint8_t port, uint8_t type);
  /** @brief Sets the low Port-Address nibble for an input port. */
  void setSwIn(uint8_t port, uint16_t portAddress);
  /** @brief Sets the low Port-Address nibble for an output port. */
  void setSwOut(uint8_t port, uint16_t portAddress);

  /** @brief Advertises one physical DMX output port. */
  void setOutputEnabled(uint8_t port);
  /** @brief Removes one advertised physical DMX output port. */
  void setOutputDisabled(uint8_t port);
  /** @brief Advertises one physical DMX input port. */
  void setInputEnabled(uint8_t port);
  /** @brief Removes one advertised physical DMX input port. */
  void setInputDisabled(uint8_t port);
  /** @brief Updates the GoodInput data-received flag. */
  void setInputDataActive(uint8_t port, bool active);
  /** @brief Updates the GoodOutputA data-transmitting flag. */
  void setOutputDataActive(uint8_t port, bool active);
  /** @brief Updates GoodOutputA merge-active and merge-mode bits. */
  void setOutputMergeStatus(
    uint8_t port,
    bool active,
    bool ltpMode);

  /** @brief Updates the DHCP-capable Status2 flag. */
  void canDHCP(bool can);
  /** @brief Updates the DHCP-configured Status2 flag. */
  void isDHCP(bool is);
  /** @brief Updates the web-configuration Status2 flag. */
  void setWebConfig(bool enabled);
  /** @brief Enables a conservative Art-Net 3 compatible reply profile. */
  void setLegacyArtNet3Mode(bool enabled);
  /** @brief Advertises programmable output-failsafe support and state. */
  void setFailsafeStatus(
    uint8_t mode,
    bool programmable);
  /** @brief Updates indicator-state and squawking status bits. */
  void setIndicatorState(ArtNetIndicatorState state);
  /** @return Current indicator state encoded in Status1. */
  ArtNetIndicatorState getIndicatorState() const;
  /** @return Advertised Art-Net binding index. */
  uint8_t getBindIndex() const;
  /** @brief Selects Locate or Normal indicator state. */
  void setSquawking(bool enabled);
  /** @return True when the squawking Status2 flag is set. */
  bool isSquawking() const;

  /** @brief Sets NetSwitch, SubSwitch, and active SwIn/SwOut values. */
  void setStartingUniverse(uint16_t startUniverse);
  /** @return Current starting Port-Address. */
  uint16_t getStartingUniverse() const;

  /** @return Mutable wire packet after incrementing NodeReport counter. */
  uint8_t* printPacket();
  /** @return Read-only pointer to the wire packet. */
  const uint8_t* data() const;
  /** @return ArtPollReply wire packet size in bytes. */
  size_t size() const;

  replyPollPacket packet;

private:
  uint16_t startingUniverse;
  uint16_t reportCode;
  uint16_t reportCounter;
  bool legacyArtNet3Mode;
  replyPollPacket transmitPacket;
  char reportText[48];

  /** @brief Clears Art-Net 4 extension fields for conservative legacy replies. */
  void applyLegacyArtNet3Profile(replyPollPacket& target);
  /** @brief Recomputes per-port SwIn and SwOut fields. */
  void updatePortAddresses();
  /** @brief Formats NodeReport from code, counter, and stored text. */
  void formatNodeReport();
};

#endif
