#include "ip_fragment_guard.h"

#include <lwip/ip4_frag.h>

// Art-Net and sACN packets are comfortably below the Ethernet/Wi-Fi MTU.
// Reassembling arbitrary fragmented IPv4 datagrams therefore provides no
// useful feature to uNode, while a maximum-size UDP datagram can monopolize
// the ESP8266 lwIP task long enough to trigger the software watchdog.
//
// These definitions satisfy every reference normally provided together by
// lwIP's ip4_frag.o. The linker consequently omits that archive object while
// the rest of the feature-enabled lwIP build, including IGMP, remains intact.

static volatile uint32_t droppedIpv4Fragments = 0;
static volatile uint32_t rejectedIpv4FragmentedTx = 0;

extern "C" struct pbuf* ip4_reass(struct pbuf* packet) {
  droppedIpv4Fragments++;

  if (packet) {
    pbuf_free(packet);
  }

  return nullptr;
}

extern "C" void ip_reass_tmr(void) {
  // No fragments are queued, so the reassembly expiry timer has no work.
}

extern "C" err_t ip4_frag(
  struct pbuf* packet,
  struct netif* interface,
  const ip4_addr_t* destination) {
  (void)packet;
  (void)interface;
  (void)destination;

  rejectedIpv4FragmentedTx++;
  return ERR_VAL;
}

bool isIpFragmentGuardEnabled() {
  return true;
}

uint32_t getDroppedIpv4FragmentCount() {
  return droppedIpv4Fragments;
}

uint32_t getRejectedIpv4FragmentedTxCount() {
  return rejectedIpv4FragmentedTx;
}
