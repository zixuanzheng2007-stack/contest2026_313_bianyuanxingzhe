/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

#ifndef EDGE_WALKER_EW_NET_STATE_H
#define EDGE_WALKER_EW_NET_STATE_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_NET_LINK_DOWN = 0,
  EW_NET_LINK_IDLE,
  EW_NET_LINK_JOINED,
  EW_NET_LINK_ONLINE
} ew_net_link_t;

typedef enum {
  EW_NET_ERR_NONE = 0,
  EW_NET_ERR_NO_WIFI,
  EW_NET_ERR_CONFIG,
  EW_NET_ERR_AUTH,
  EW_NET_ERR_TLS,
  EW_NET_ERR_TIMEOUT,
  EW_NET_ERR_AT_BUSY,
  EW_NET_ERR_RESPONSE
} ew_net_error_t;

typedef struct {
  ew_net_link_t link;
  ew_net_error_t error;
  char ip[24];
  unsigned long generation;
} ew_net_snapshot_t;

void ew_net_state_publish(ew_net_link_t link, const char *ip);
void ew_net_state_error(ew_net_error_t error);
int ew_net_state_snapshot(ew_net_snapshot_t *out);

#ifdef __cplusplus
}
#endif

#endif
