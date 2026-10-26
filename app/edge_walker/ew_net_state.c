/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

#include "ew_net_state.h"

#include <pthread.h>
#include <stdio.h>
#include <string.h>

static pthread_mutex_t g_state_mu = PTHREAD_MUTEX_INITIALIZER;
static ew_net_snapshot_t g_state = {
  EW_NET_LINK_DOWN, EW_NET_ERR_NONE, "", 0
};

void ew_net_state_publish(ew_net_link_t link, const char *ip)
{
  pthread_mutex_lock(&g_state_mu);
  g_state.link = link;
  g_state.error = EW_NET_ERR_NONE;
  snprintf(g_state.ip, sizeof(g_state.ip), "%s", ip ? ip : "");
  g_state.generation++;
  pthread_mutex_unlock(&g_state_mu);
}

void ew_net_state_error(ew_net_error_t error)
{
  pthread_mutex_lock(&g_state_mu);
  g_state.error = error;
  g_state.generation++;
  pthread_mutex_unlock(&g_state_mu);
}

int ew_net_state_snapshot(ew_net_snapshot_t *out)
{
  if (out == NULL) {
    return -1;
  }
  pthread_mutex_lock(&g_state_mu);
  *out = g_state;
  pthread_mutex_unlock(&g_state_mu);
  return 0;
}
