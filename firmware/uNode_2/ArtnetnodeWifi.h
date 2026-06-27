#ifndef ARTNETNODEWIFI_H
#define ARTNETNODEWIFI_H
/*

Copyright (c) Charles Yarnold charlesyarnold@gmail.com 2015

Copyright (c) 2016 Stephan Ruloff
https://github.com/rstephan

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, under version 2 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

*/

#include <Arduino.h>
#if defined(ARDUINO_ARCH_ESP32) || defined(ESP32)
#include <WiFi.h>
#elif defined(ARDUINO_ARCH_ESP8266)
#include <ESP8266WiFi.h>
#elif defined(ARDUINO_ARCH_SAMD)
#if defined(ARDUINO_SAMD_MKR1000)
#include <WiFi101.h>
#else
#include <WiFiNINA.h>
#endif
#else
#error "Architecture not supported!"
#endif
#include <WiFiUdp.h>
#include "OpCodes.h"
#include "NodeReportCodes.h"
#include "StyleCodes.h"
#include "PriorityCodes.h"
#include "ProtocolSettings.h"
#include "PollReply.h"

struct ArtPollReplyInfo {
  IPAddress senderIP;
  IPAddress reportedIP;
  char portName[19];
  uint8_t bindIndex;
  uint8_t netSwitch;
  uint8_t subSwitch;
  uint8_t numPorts;
  uint8_t portTypes[4];
  uint8_t swIn[4];
  uint8_t swOut[4];
};

struct ArtAddressInfo {
  IPAddress senderIP;
  uint8_t netSwitch;
  uint8_t bindIndex;
  char portName[19];
  char longName[65];
  uint8_t swIn[4];
  uint8_t swOut[4];
  uint8_t subSwitch;
  uint8_t acnPriority;
  uint8_t command;
};

struct ArtIpProgInfo {
  IPAddress senderIP;
  uint8_t command;
  IPAddress ip;
  IPAddress subnet;
  IPAddress gateway;
  uint16_t port;
};

struct ArtIpProgReplyInfo {
  IPAddress ip;
  IPAddress subnet;
  IPAddress gateway;
  uint16_t port;
  bool dhcp;
};

struct ArtNetParserDiagnostics {
  uint32_t oversizedPackets;
  uint32_t shortPackets;
  uint32_t invalidIdPackets;
  uint32_t unsupportedProtocolPackets;
  uint32_t malformedPackets;
  uint32_t unsupportedOpcodes;
};

class ArtnetnodeWifi {
public:
  /** @brief Initializes protocol state and internal DMX buffers. */
  ArtnetnodeWifi();

  /** @brief Binds the Art-Net UDP socket and refreshes interface identity. */
  uint8_t begin(String hostname = "");
  /** @brief Processes one pending Art-Net datagram and deferred replies. */
  uint16_t read();

  // Node identity
  /** @brief Sets the advertised Art-Net Port Name. */
  void setShortName(const char name[]);
  /** @brief Sets the advertised Art-Net Long Name. */
  void setLongName(const char name[]);
  /** @brief Sets both advertised names to the same value. */
  void setName(const char name[]);
  /** @brief Sets the advertised number of ports. */
  void setNumPorts(uint8_t num);
  /** @brief Sets the ArtPollReply NodeReport status. */
  void setNodeReport(
    uint16_t code,
    const char* text);
  /** @brief Sets the starting 15-bit Port-Address. */
  void setStartingUniverse(uint16_t startingUniverse);
  /** @brief Sets the advertised firmware version bytes. */
  void setFirmwareVersion(uint8_t high, uint8_t low);

  // Transmit
  /** @return UDP result for ArtDmx sent to the configured host name. */
  int write(void);
  /** @return UDP result for ArtDmx sent to one IP address. */
  int write(IPAddress ip);
  /** @return Number of IP targets that accepted the same ArtDmx frame. */
  uint8_t write(
    const IPAddress targets[],
    uint8_t targetCount);
  /** @return UDP result for an ArtPoll sent to the given IP address. */
  int sendArtPoll(IPAddress ip);
  /** @brief Sets one zero-based byte in the outgoing ArtDmx payload. */
  void setByte(uint16_t pos, uint8_t value);
  /** @brief Sets the outgoing ArtDmx Port-Address. */
  void setUniverse(uint16_t universe);

  /** @brief Sets the ArtDmx physical input port field. */
  inline void setPhysical(uint8_t port) {
    physical = port;
  }

  /** @brief Sets outgoing ArtDmx payload length, clamped to 512. */
  void setLength(uint16_t len);

  /** @brief Sets one raw ArtPollReply PortTypes entry. */
  inline void setPortType(uint8_t port, uint8_t type) {
    PollReplyPacket.setPortType(port, type);
  }

  /** @brief Updates the advertised DHCP-capable flag. */
  inline void canDHCP(bool can) {
    PollReplyPacket.canDHCP(can);
  }

  /** @brief Updates the advertised DHCP-configured flag. */
  inline void isDHCP(bool is) {
    PollReplyPacket.isDHCP(is);
  }

  /** @brief Enables a conservative Art-Net 3 compatible ArtPollReply profile. */
  inline void setLegacyArtNet3Mode(bool enabled) {
    PollReplyPacket.setLegacyArtNet3Mode(enabled);
  }

  // DMX controls
  /** @brief Configures the single advertised port direction. */
  void setDirection(bool outputMode);
  /** @brief Updates physical DMX input activity status. */
  void setPortInputActive(bool active);
  /** @brief Updates physical DMX output activity status. */
  void setPortOutputActive(bool active);
  /** @brief Updates physical DMX output merge status. */
  void setPortOutputMergeStatus(
    bool active,
    bool ltpMode);
  /** @brief Updates ArtPollReply output-failsafe Status3 bits. */
  void setFailsafeStatus(
    uint8_t mode,
    bool programmable);
  /** @brief Updates ArtPollReply indicator state. */
  void setIndicatorState(ArtNetIndicatorState state);
  /** @return Current ArtPollReply indicator state. */
  ArtNetIndicatorState getIndicatorState() const;
  /** @brief Enables legacy internal DMX processing. */
  void enableDMX();
  /** @brief Disables legacy internal DMX processing. */
  void disableDMX();
  /** @brief Enables one configured legacy DMX output. */
  void enableDMXOutput(uint8_t outputID);
  /** @brief Disables one configured legacy DMX output. */
  void disableDMXOutput(uint8_t outputID);

  /** @brief Associates a legacy DMX output with a UART and Port-Address. */
  uint8_t setDMXOutput(uint8_t outputID, uint8_t uartNum, uint16_t attachedUniverse);

  // Return a pointer to the start of the DMX data
  /** @return Pointer to the current incoming ArtDmx payload buffer. */
  inline uint8_t* getDmxFrame(void) {
    return artnetPacket + ARTNET_DMX_START_LOC;
  }

  /** @brief Registers the zero-start-code ArtDmx callback. */
  inline void setArtDmxCallback(void (*fptr)(uint16_t universe, uint16_t length, uint8_t sequence, uint8_t* data)) {
    artDmxCallback = fptr;
  }

  /** @brief Registers the non-zero-start-code ArtNzs callback. */
  inline void setArtNzsCallback(void (*fptr)(uint16_t universe, uint16_t length, uint8_t sequence, uint8_t startCode, uint8_t* data)) {
    artNzsCallback = fptr;
  }

  /** @brief Registers the ArtSync callback. */
  inline void setArtSyncCallback(void (*fptr)()) {
    artSyncCallback = fptr;
  }

  /** @brief Registers the parsed ArtPollReply callback. */
  inline void setArtPollReplyCallback(
      void (*fptr)(const ArtPollReplyInfo& info)) {
    artPollReplyCallback = fptr;
  }

  /** @brief Registers the parsed ArtAddress callback. */
  inline void setArtAddressCallback(
      void (*fptr)(const ArtAddressInfo& info)) {
    artAddressCallback = fptr;
  }

  /** @brief Registers the parsed ArtIpProg callback. */
  inline void setArtIpProgCallback(
      bool (*fptr)(const ArtIpProgInfo& info,
                   ArtIpProgReplyInfo& reply)) {
    artIpProgCallback = fptr;
  }

  /** @return IP address that sent the most recently parsed datagram. */
  inline IPAddress& getSenderIp(void) {
    return senderIp;
  }

  /** @return ArtDmx Physical field from the most recently parsed datagram. */
  inline uint8_t getIncomingPhysical(void) const {
    return incomingPhysical;
  }

  /** @return Number of attempted ArtPollReply transmissions. */
  inline uint32_t getPollCount() {
    return artPollCounter;
  }

  /** @return Current starting 15-bit Port-Address. */
  inline uint16_t getStartingUniverse() const {
    return startingUniverse;
  }

  /** @brief Selects Locate or Normal indicator state. */
  inline void setSquawking(bool enabled) {
    PollReplyPacket.setSquawking(enabled);
  }

  /** @return True when Locate/squawking state is active. */
  inline bool isSquawking(void) {
    return PollReplyPacket.isSquawking();
  }

  /** @return millis() timestamp of the last ArtPollReply attempt. */
  inline uint32_t getLastPollMillis() {
    return lastPollMillis;
  }

  /** @return Low-level Art-Net parser diagnostic counters. */
  inline const ArtNetParserDiagnostics& getParserDiagnostics() const {
    return parserDiagnostics;
  }

  static const char artnetId[];

private:
  WiFiUDP Udp;
  PollReply PollReplyPacket;
  String host;
  IPAddress senderIp;

  // Packet handlers
  /** @brief Validates and dispatches an ArtDmx or ArtNzs payload. */
  uint16_t handleDMX(uint8_t nzs);
  /** @brief Sends an immediate unicast ArtPollReply. */
  uint16_t sendPollReply(IPAddress requester);
  /** @brief Parses an ArtPollReply into the public callback structure. */
  uint16_t handlePollReply();
  /** @brief Parses ArtAddress, invokes the callback, and replies. */
  uint16_t handleArtAddress();
  /** @brief Parses ArtIpProg, invokes the callback, and replies. */
  uint16_t handleArtIpProg();
  /** @brief Sends an ArtIpProgReply to one controller. */
  uint16_t sendIpProgReply(
    IPAddress requester,
    const ArtIpProgReplyInfo& info);
  /** @brief Populates current network settings for ArtIpProgReply. */
  void getCurrentIpProgReplyInfo(
    ArtIpProgReplyInfo& info) const;
  /** @brief Adds a requester to the delayed ArtPollReply queue. */
  void queuePollReply(IPAddress requester);
  /** @brief Sends delayed ArtPollReply entries whose deadlines elapsed. */
  void processPendingPollReplies();
  /** @brief Consumes and drops an oversized UDP datagram. */
  void discardUdpPacket(int length);
  /** @return True when the current packet declares protocol version 14+. */
  bool hasSupportedProtocolVersion() const;
  /** @return True when a targeted ArtPoll includes this node. */
  bool isTargetedPollForThisNode() const;

  // Packet vars
  uint8_t artnetPacket[ARTNET_MAX_BUFFER];
  uint16_t packetSize;
  uint16_t opcode;
  uint8_t sequence;
  uint8_t physical;
  uint8_t incomingPhysical;
  uint16_t outgoingUniverse;
  uint16_t dmxDataLength;
  IPAddress localIP;

  // Packet functions
  /** @return Even ArtDmx payload length, or zero when configuration is invalid. */
  uint16_t makePacket(void);

  struct PendingPollReply {
    IPAddress requester;
    uint32_t dueMillis;
    bool active;
  };

  static const uint8_t MAX_PENDING_POLL_REPLIES = 4;
  PendingPollReply pendingPollReplies[MAX_PENDING_POLL_REPLIES];

  // DMX settings
  bool DMXOutputStatus;
  uint16_t DMXOutputs[DMX_MAX_OUTPUTS][3];
  uint8_t DMXBuffer[DMX_MAX_OUTPUTS][DMX_MAX_BUFFER];

  uint16_t startingUniverse;

  // DMX tick
  /** @return Legacy output frame pointer, or nullptr for an invalid output. */
  uint8_t* getDmxFrame(uint8_t outputID);

  uint32_t artPollCounter = 0;
  uint32_t lastPollMillis = 0;
  ArtNetParserDiagnostics parserDiagnostics = {};

  void (*artDmxCallback)(uint16_t universe, uint16_t length, uint8_t sequence, uint8_t* data);
  void (*artNzsCallback)(uint16_t universe, uint16_t length, uint8_t sequence, uint8_t startCode, uint8_t* data);
  void (*artSyncCallback)();
  void (*artPollReplyCallback)(const ArtPollReplyInfo& info);
  void (*artAddressCallback)(const ArtAddressInfo& info);
  bool (*artIpProgCallback)(const ArtIpProgInfo& info,
                            ArtIpProgReplyInfo& reply);
};

#endif
