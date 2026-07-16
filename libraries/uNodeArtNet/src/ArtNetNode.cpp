/*

Copyright (c) Charles Yarnold charlesyarnold@gmail.com 2015

Copyright (c) 2016-2020 Stephan Ruloff
https://github.com/rstephan/ArtnetnodeWifi

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

#include <ArtNetNode.h>


const char ArtNetNode::artnetId[] = ARTNET_ID;

ArtNetNode::ArtNetNode(UDP& udp)
  : Udp(udp) {
  sequence = 1;
  physical = 0;
  incomingPhysical = 0;
  outgoingUniverse = 0;
  dmxDataLength = 0;
  packetSize = 0;
  oversizedPacketBytesRemaining = 0;
  discardUnreadPacketOnNextParse = false;
  opcode = 0;
  networkConfig = {};
  senderIp = IPAddress();
  startingUniverse = 0;
  artDmxCallback = nullptr;
  artNzsCallback = nullptr;
  artSyncCallback = nullptr;
  artPollReplyCallback = nullptr;
  artAddressCallback = nullptr;
  artIpProgCallback = nullptr;

  for (uint8_t i = 0; i < MAX_PENDING_POLL_REPLIES; i++) {
    pendingPollReplies[i].active = false;
    pendingPollReplies[i].dueMillis = 0;
  }
}

/**
@retval 0 Ok
*/
uint8_t ArtNetNode::begin(const ArtNetNetworkConfig& network) {
  Udp.stop();
  oversizedPacketBytesRemaining = 0;
  if (!Udp.begin(ARTNET_PORT)) {
    return 1;
  }

  networkConfig = network;
  PollReplyPacket.setMac(networkConfig.mac);
  PollReplyPacket.setIP(networkConfig.ip);
  PollReplyPacket.setBindIP(networkConfig.ip);
  PollReplyPacket.canDHCP(true);
  PollReplyPacket.isDHCP(networkConfig.dhcp);
  PollReplyPacket.setWebConfig(true);

  for (uint8_t i = 0; i < MAX_PENDING_POLL_REPLIES; i++) {
    pendingPollReplies[i].active = false;
  }

  return 0;
}

void ArtNetNode::setShortName(const char name[]) {
  PollReplyPacket.setShortName(name);
}

void ArtNetNode::setLongName(const char name[]) {
  PollReplyPacket.setLongName(name);
}

void ArtNetNode::setName(const char name[]) {
  PollReplyPacket.setShortName(name);
  PollReplyPacket.setLongName(name);
}

void ArtNetNode::setNumPorts(uint8_t num) {
  PollReplyPacket.setNumPorts(num);
}

void ArtNetNode::setNodeReport(
  uint16_t code,
  const char* text) {
  PollReplyPacket.setNodeReport(
    code,
    text);
}

void ArtNetNode::setDirection(bool outputMode) {
  PollReplyPacket.clearPorts();

  if (outputMode) {
    PollReplyPacket.setOutputEnabled(0);
  } else {
    PollReplyPacket.setInputEnabled(0);
  }

  PollReplyPacket.setNumPorts(1);
}

void ArtNetNode::setPortInputActive(bool active) {
  PollReplyPacket.setInputDataActive(0, active);
}

void ArtNetNode::setPortOutputActive(bool active) {
  PollReplyPacket.setOutputDataActive(0, active);
}

void ArtNetNode::setPortOutputMergeStatus(
  bool active,
  bool ltpMode) {
  PollReplyPacket.setOutputMergeStatus(
    0,
    active,
    ltpMode);
}

void ArtNetNode::setFailsafeStatus(
  uint8_t mode,
  bool programmable) {
  PollReplyPacket.setFailsafeStatus(
    mode,
    programmable);
}

void ArtNetNode::setIndicatorState(
  ArtNetIndicatorState state) {
  PollReplyPacket.setIndicatorState(state);
}

ArtNetIndicatorState ArtNetNode::getIndicatorState() const {
  return PollReplyPacket.getIndicatorState();
}

void ArtNetNode::setStartingUniverse(uint16_t startingUniverse) {
  this->startingUniverse = min(startingUniverse, (uint16_t)0x7fff);
  PollReplyPacket.setStartingUniverse(startingUniverse);
}

void ArtNetNode::setFirmwareVersion(uint8_t high, uint8_t low) {
  PollReplyPacket.setFirmwareVersion(high, low);
}

void ArtNetNode::setUniverse(uint16_t universe) {
  outgoingUniverse = min(universe, (uint16_t)0x7fff);
}

void ArtNetNode::setLength(uint16_t len) {
  dmxDataLength = min(len, (uint16_t)DMX_MAX_BUFFER);
}

uint16_t ArtNetNode::read() {
  uint8_t startcode;

  processPendingPollReplies();

  if (oversizedPacketBytesRemaining > 0) {
    discardOversizedPacketChunk();
    return 0;
  }

  const int parsedSize = Udp.parsePacket();

  if (parsedSize <= 0) {
    return 0;
  }

  if (parsedSize > ARTNET_MAX_BUFFER) {
    parserDiagnostics.oversizedPackets++;

    if (!discardUnreadPacketOnNextParse) {
      oversizedPacketBytesRemaining = parsedSize;
      discardOversizedPacketChunk();
    }

    return 0;
  }

  packetSize = parsedSize;

  if (Udp.read(artnetPacket, packetSize) != packetSize) {
    parserDiagnostics.malformedPackets++;
    return 0;
  }

  if (packetSize >= 10) {
    senderIp = Udp.remoteIP();

    // Check that packetID is "Art-Net" else ignore
    if (memcmp(artnetPacket, artnetId, sizeof(artnetId)) != 0) {
      parserDiagnostics.invalidIdPackets++;
      return 0;
    }

    opcode = artnetPacket[8] | artnetPacket[9] << 8;

    switch (opcode) {
      case OpDmx:
        if (packetSize < ARTNET_DMX_START_LOC) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        return handleDMX(0);
      case OpPoll:
        if (packetSize < ARTNET_POLL_MIN_LENGTH) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        if (!isTargetedPollForThisNode()) {
          return 0;
        }
        queuePollReply(senderIp);
        break;
      case OpNzs:
        if (packetSize < ARTNET_DMX_START_LOC) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        startcode = artnetPacket[13];
        if (startcode != 0 && startcode != DMX_RDM_STARTCODE) {
          return handleDMX(startcode);
        }
        break;
      case OpSync:
        if (packetSize < ARTNET_SYNC_MIN_LENGTH) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        if (artSyncCallback) {
          (*artSyncCallback)();
        }
        return OpSync;
      case OpPollReply:
        if (packetSize < ARTNET_POLL_REPLY_MIN_LENGTH) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        return handlePollReply();

      case OpAddress:
        if (packetSize < ARTNET_ADDRESS_MIN_LENGTH) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        return handleArtAddress();

      case OpIpProg:
        if (packetSize < ARTNET_IP_PROG_MIN_LENGTH) {
          parserDiagnostics.malformedPackets++;
          return 0;
        }
        if (!hasSupportedProtocolVersion()) {
          parserDiagnostics.unsupportedProtocolPackets++;
          return 0;
        }
        return handleArtIpProg();

      default:
        parserDiagnostics.unsupportedOpcodes++;
        break;
    }

    return opcode;
  }

  parserDiagnostics.shortPackets++;
  return 0;
}

void ArtNetNode::discardOversizedPacketChunk() {
  static const size_t DISCARD_CHUNK_SIZE = 256;
  uint8_t discard[DISCARD_CHUNK_SIZE];

  const size_t requested = min(
    (size_t)oversizedPacketBytesRemaining,
    DISCARD_CHUNK_SIZE);
  const int bytesRead = Udp.read(discard, requested);

  if (bytesRead <= 0) {
    // A transport may already have released the current datagram. Avoid
    // stalling all future packets when no more bytes can be consumed.
    oversizedPacketBytesRemaining = 0;
    return;
  }

  oversizedPacketBytesRemaining -= bytesRead;
}

bool ArtNetNode::hasSupportedProtocolVersion() const {
  if (packetSize < 12) {
    return false;
  }

  const uint16_t version =
    ((uint16_t)artnetPacket[10] << 8)
    | artnetPacket[11];

  return version >= ARTNET_PROTOCOL_VERSION;
}

bool ArtNetNode::isTargetedPollForThisNode() const {
  if ((artnetPacket[12] & 0x20) == 0) {
    return true;
  }

  const uint16_t top =
    packetSize >= 16
      ? ((uint16_t)artnetPacket[14] << 8) | artnetPacket[15]
      : 0;
  const uint16_t bottom =
    packetSize >= 18
      ? ((uint16_t)artnetPacket[16] << 8) | artnetPacket[17]
      : 0;

  return startingUniverse >= bottom
         && startingUniverse <= top;
}

uint16_t ArtNetNode::makePacket(void) {
  if (dmxDataLength < 2
      || dmxDataLength > DMX_MAX_BUFFER) {
    return 0;
  }

  memcpy(artnetPacket, artnetId, sizeof(artnetId));
  opcode = OpDmx;
  artnetPacket[8] = opcode & 0xff;
  artnetPacket[9] = opcode >> 8;
  artnetPacket[10] = ARTNET_PROTOCOL_VERSION >> 8;
  artnetPacket[11] = ARTNET_PROTOCOL_VERSION & 0xff;
  artnetPacket[12] = sequence;
  sequence++;
  if (!sequence) {
    sequence = 1;
  }
  artnetPacket[13] = physical;
  artnetPacket[14] = outgoingUniverse & 0xff;
  artnetPacket[15] = (outgoingUniverse >> 8) & 0x7f;

  uint16_t len = dmxDataLength;
  if (len & 1) {
    artnetPacket[ARTNET_DMX_START_LOC + len] = 0;
    len++;
  }

  artnetPacket[16] = len >> 8;
  artnetPacket[17] = len & 0xff;

  return len;
}

int ArtNetNode::write(IPAddress ip) {
  uint16_t len;

  len = makePacket();
  if (!len || !Udp.beginPacket(ip, ARTNET_PORT)) {
    return 0;
  }

  const size_t packetLength = ARTNET_DMX_START_LOC + len;
  if (Udp.write(artnetPacket, packetLength) != packetLength) {
    Udp.endPacket();
    return 0;
  }

  return Udp.endPacket();
}

uint8_t ArtNetNode::write(
  const IPAddress targets[],
  uint8_t targetCount) {
  if (!targets || targetCount == 0) {
    return 0;
  }

  const uint16_t len = makePacket();
  if (!len) {
    return 0;
  }

  const size_t packetLength = ARTNET_DMX_START_LOC + len;
  uint8_t sentCount = 0;

  for (uint8_t i = 0; i < targetCount; i++) {
    if (!Udp.beginPacket(targets[i], ARTNET_PORT)) {
      continue;
    }

    if (Udp.write(artnetPacket, packetLength) != packetLength) {
      Udp.endPacket();
      continue;
    }

    if (Udp.endPacket()) {
      sentCount++;
    }
  }

  return sentCount;
}

int ArtNetNode::sendArtPoll(IPAddress ip) {
  uint8_t pollPacket[14] = { 0 };

  memcpy(
    pollPacket,
    artnetId,
    sizeof(artnetId));

  pollPacket[8] = (uint8_t)(OpPoll & 0xff);
  pollPacket[9] = (uint8_t)(OpPoll >> 8);
  pollPacket[10] = ARTNET_PROTOCOL_VERSION >> 8;
  pollPacket[11] = ARTNET_PROTOCOL_VERSION & 0xff;
  pollPacket[12] = 0;
  pollPacket[13] = 0x10;

  if (!Udp.beginPacket(ip, ARTNET_PORT)) {
    return 0;
  }

  if (Udp.write(pollPacket, sizeof(pollPacket))
      != sizeof(pollPacket)) {
    Udp.endPacket();
    return 0;
  }

  return Udp.endPacket();
}

void ArtNetNode::setByte(uint16_t pos, uint8_t value) {
  if (pos >= 512) {
    return;
  }
  artnetPacket[ARTNET_DMX_START_LOC + pos] = value;
}


uint16_t ArtNetNode::handleDMX(uint8_t nzs) {
  // Get universe
  uint16_t universe = artnetPacket[14] | artnetPacket[15] << 8;

  // Get DMX frame length
  uint16_t dmxDataLength = artnetPacket[17] | artnetPacket[16] << 8;

  const uint16_t minimumLength = nzs ? 1 : 2;

  if (dmxDataLength < minimumLength
      || dmxDataLength > DMX_MAX_BUFFER
      || (!nzs && (dmxDataLength & 1))
      || dmxDataLength > packetSize - ARTNET_DMX_START_LOC) {
    parserDiagnostics.malformedPackets++;
    return 0;
  }

  // Sequence
  uint8_t sequence = artnetPacket[12];
  incomingPhysical = artnetPacket[13];

  if (!nzs && artDmxCallback) {
    (*artDmxCallback)(universe, dmxDataLength, sequence, artnetPacket + ARTNET_DMX_START_LOC);
  } else if (nzs && artNzsCallback) {
    (*artNzsCallback)(universe, dmxDataLength, sequence, nzs, artnetPacket + ARTNET_DMX_START_LOC);
  }

  if (nzs) {
    return OpNzs;
  } else {
    return OpDmx;
  }
}

uint16_t ArtNetNode::sendPollReply(IPAddress requester) {

  artPollCounter++;
  lastPollMillis = millis();
  if (!Udp.beginPacket(requester, ARTNET_PORT)) {
    return 0;
  }

  const size_t replyLength = PollReplyPacket.size();
  if (Udp.write(PollReplyPacket.printPacket(), replyLength)
      != replyLength) {
    Udp.endPacket();
    return 0;
  }

  if (!Udp.endPacket()) {
    return 0;
  }

  return OpPoll;
}

void ArtNetNode::queuePollReply(IPAddress requester) {
  for (uint8_t i = 0; i < MAX_PENDING_POLL_REPLIES; i++) {
    if (pendingPollReplies[i].active
        && pendingPollReplies[i].requester == requester) {
      return;
    }
  }

  for (uint8_t i = 0; i < MAX_PENDING_POLL_REPLIES; i++) {
    if (!pendingPollReplies[i].active) {
      pendingPollReplies[i].requester = requester;
      pendingPollReplies[i].dueMillis = millis() + random(1000);
      pendingPollReplies[i].active = true;
      return;
    }
  }
}

void ArtNetNode::processPendingPollReplies() {
  const uint32_t now = millis();

  for (uint8_t i = 0; i < MAX_PENDING_POLL_REPLIES; i++) {
    if (pendingPollReplies[i].active
        && (int32_t)(now - pendingPollReplies[i].dueMillis) >= 0) {
      const IPAddress requester = pendingPollReplies[i].requester;
      pendingPollReplies[i].active = false;
      sendPollReply(requester);
    }
  }
}

uint16_t ArtNetNode::handlePollReply() {
  ArtPollReplyInfo info;

  info.senderIP = senderIp;
  info.reportedIP = IPAddress(
    artnetPacket[10],
    artnetPacket[11],
    artnetPacket[12],
    artnetPacket[13]);
  memcpy(info.portName, artnetPacket + 26, 18);
  info.portName[18] = '\0';
  info.netSwitch = artnetPacket[18] & 0x7f;
  info.subSwitch = artnetPacket[19] & 0x0f;
  info.numPorts = min(
    (uint16_t)(((uint16_t)artnetPacket[172] << 8)
               | artnetPacket[173]),
    (uint16_t)4);
  memcpy(info.portTypes, artnetPacket + 174, 4);
  memcpy(info.swIn, artnetPacket + 186, 4);
  memcpy(info.swOut, artnetPacket + 190, 4);
  info.bindIndex =
    packetSize > 211
      ? artnetPacket[211]
      : 0;

  if (artPollReplyCallback) {
    (*artPollReplyCallback)(info);
  }

  return OpPollReply;
}

uint16_t ArtNetNode::handleArtAddress() {
  const uint8_t bindIndex = artnetPacket[13];

  if (bindIndex != PollReplyPacket.getBindIndex()) {
    return 0;
  }

  ArtAddressInfo info;
  info.senderIP = senderIp;
  info.netSwitch = artnetPacket[12];
  info.bindIndex = bindIndex;
  memcpy(info.portName, artnetPacket + 14, 18);
  info.portName[18] = '\0';
  memcpy(info.longName, artnetPacket + 32, 64);
  info.longName[64] = '\0';
  memcpy(info.swIn, artnetPacket + 96, 4);
  memcpy(info.swOut, artnetPacket + 100, 4);
  info.subSwitch = artnetPacket[104];
  info.acnPriority = artnetPacket[105];
  info.command = artnetPacket[106];

  if (artAddressCallback) {
    (*artAddressCallback)(info);
  }

  sendPollReply(senderIp);
  return OpAddress;
}

void ArtNetNode::getCurrentIpProgReplyInfo(
  ArtIpProgReplyInfo& info) const {
  info.ip = networkConfig.ip;
  info.subnet = networkConfig.subnet;
  info.gateway = networkConfig.gateway;
  info.port = ARTNET_PORT;
  info.dhcp = networkConfig.dhcp;
}

uint16_t ArtNetNode::sendIpProgReply(
  IPAddress requester,
  const ArtIpProgReplyInfo& info) {
  uint8_t reply[ARTNET_IP_PROG_REPLY_LENGTH] = { 0 };

  memcpy(reply, artnetId, sizeof(artnetId));
  reply[8] = OpIpProgReply & 0xff;
  reply[9] = OpIpProgReply >> 8;
  reply[10] = ARTNET_PROTOCOL_VERSION >> 8;
  reply[11] = ARTNET_PROTOCOL_VERSION & 0xff;

  for (uint8_t i = 0; i < 4; i++) {
    reply[16 + i] = info.ip[i];
    reply[20 + i] = info.subnet[i];
    reply[28 + i] = info.gateway[i];
  }

  reply[24] = info.port >> 8;
  reply[25] = info.port & 0xff;

  if (info.dhcp) {
    reply[26] = 0x40;
  }

  if (!Udp.beginPacket(requester, ARTNET_PORT)) {
    return 0;
  }

  if (Udp.write(reply, sizeof(reply)) != sizeof(reply)) {
    Udp.endPacket();
    return 0;
  }

  if (!Udp.endPacket()) {
    return 0;
  }

  return OpIpProgReply;
}

uint16_t ArtNetNode::handleArtIpProg() {
  ArtIpProgInfo info;
  ArtIpProgReplyInfo reply;

  info.senderIP = senderIp;
  info.command = artnetPacket[14];
  info.ip = IPAddress(
    artnetPacket[16],
    artnetPacket[17],
    artnetPacket[18],
    artnetPacket[19]);
  info.subnet = IPAddress(
    artnetPacket[20],
    artnetPacket[21],
    artnetPacket[22],
    artnetPacket[23]);
  info.port =
    ((uint16_t)artnetPacket[24] << 8)
    | artnetPacket[25];

  if (packetSize >= 30) {
    info.gateway = IPAddress(
      artnetPacket[26],
      artnetPacket[27],
      artnetPacket[28],
      artnetPacket[29]);
  } else {
    info.gateway = IPAddress();
  }

  getCurrentIpProgReplyInfo(reply);

  if (artIpProgCallback) {
    (*artIpProgCallback)(
      info,
      reply);
  }

  sendIpProgReply(
    senderIp,
    reply);

  return OpIpProg;
}
