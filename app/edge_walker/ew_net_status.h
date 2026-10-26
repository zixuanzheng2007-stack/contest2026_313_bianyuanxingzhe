/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * Stable network and LLM fault codes for display, logs and acceptance.
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_NET_STATUS_H
#define EDGE_WALKER_EW_NET_STATUS_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_NET_FAULT_OK = 0,
  EW_NET_FAULT_NO_MODEM,
  EW_NET_FAULT_NO_CREDENTIALS,
  EW_NET_FAULT_AP_NOT_FOUND,
  EW_NET_FAULT_BAD_PASSWORD,
  EW_NET_FAULT_JOIN_TIMEOUT,
  EW_NET_FAULT_JOIN_FAILED,
  EW_NET_FAULT_LAN_ONLY,
  EW_NET_FAULT_TLS_TIMEOUT,
  EW_NET_FAULT_TLS_FAILED,
  EW_NET_FAULT_HTTP_TIMEOUT,
  EW_NET_FAULT_HTTP_AUTH,
  EW_NET_FAULT_HTTP_RATE_LIMIT,
  EW_NET_FAULT_HTTP_SERVER,
  EW_NET_FAULT_HTTP_BAD,
  EW_NET_FAULT_CONFIG_MISSING,
  EW_NET_FAULT_CONFIG_INVALID,
  EW_NET_FAULT_API_KEY_MISSING,
  EW_NET_FAULT_REQUEST_TOO_LONG,
  EW_NET_FAULT_LLM_REPLY_BAD,
  EW_NET_FAULT_RESPONSE,
  EW_NET_FAULT_BUSY
} ew_net_fault_t;

const char *ew_net_fault_code(ew_net_fault_t fault);
const char *ew_net_fault_text(ew_net_fault_t fault);

/* Return the HTTP status code, or -1 when no valid status line is present. */
int ew_net_http_status(const char *raw);
ew_net_fault_t ew_net_fault_from_http_status(int status);

/* Map ESP-AT +CWJAP:<code> and common failure text to a user-facing fault. */
ew_net_fault_t ew_net_fault_from_join_response(const char *response);

/* Replace one secret value with *** before writing diagnostic text. */
int ew_net_redact_secret(const char *input, const char *secret,
                         char *output, unsigned output_size);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_NET_STATUS_H */
