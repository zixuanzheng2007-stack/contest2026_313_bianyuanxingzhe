/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

#include "ew_net_status.h"

#include <stdio.h>
#include <string.h>

const char *ew_net_fault_code(ew_net_fault_t fault)
{
  switch (fault)
    {
      case EW_NET_FAULT_OK:               return "ok";
      case EW_NET_FAULT_NO_MODEM:         return "no_modem";
      case EW_NET_FAULT_NO_CREDENTIALS:   return "no_credentials";
      case EW_NET_FAULT_AP_NOT_FOUND:     return "ap_not_found";
      case EW_NET_FAULT_BAD_PASSWORD:     return "bad_password";
      case EW_NET_FAULT_JOIN_TIMEOUT:     return "join_timeout";
      case EW_NET_FAULT_JOIN_FAILED:      return "join_failed";
      case EW_NET_FAULT_LAN_ONLY:         return "lan_only";
      case EW_NET_FAULT_TLS_TIMEOUT:      return "tls_timeout";
      case EW_NET_FAULT_TLS_FAILED:       return "tls_failed";
      case EW_NET_FAULT_HTTP_TIMEOUT:     return "http_timeout";
      case EW_NET_FAULT_HTTP_AUTH:        return "http_auth";
      case EW_NET_FAULT_HTTP_RATE_LIMIT:  return "http_rate_limit";
      case EW_NET_FAULT_HTTP_SERVER:      return "http_server";
      case EW_NET_FAULT_HTTP_BAD:         return "http_bad";
      case EW_NET_FAULT_CONFIG_MISSING:   return "config_missing";
      case EW_NET_FAULT_CONFIG_INVALID:   return "config_invalid";
      case EW_NET_FAULT_API_KEY_MISSING:  return "api_key_missing";
      case EW_NET_FAULT_REQUEST_TOO_LONG: return "request_too_long";
      case EW_NET_FAULT_LLM_REPLY_BAD:    return "llm_reply_bad";
      case EW_NET_FAULT_RESPONSE:         return "bad_response";
      case EW_NET_FAULT_BUSY:             return "busy";
      default:                            return "unknown";
    }
}

const char *ew_net_fault_text(ew_net_fault_t fault)
{
  switch (fault)
    {
      case EW_NET_FAULT_OK:               return "READY";
      case EW_NET_FAULT_NO_MODEM:         return "NO MODEM: check AT module";
      case EW_NET_FAULT_NO_CREDENTIALS:   return "NO WIFI: choose an AP";
      case EW_NET_FAULT_AP_NOT_FOUND:     return "AP NOT FOUND: rescan";
      case EW_NET_FAULT_BAD_PASSWORD:     return "BAD PASSWORD: re-enter";
      case EW_NET_FAULT_JOIN_TIMEOUT:     return "JOIN TIMEOUT: retry";
      case EW_NET_FAULT_JOIN_FAILED:      return "JOIN FAIL: check router";
      case EW_NET_FAULT_LAN_ONLY:         return "LAN ONLY: no internet";
      case EW_NET_FAULT_TLS_TIMEOUT:      return "TLS TIMEOUT: retry later";
      case EW_NET_FAULT_TLS_FAILED:       return "TLS FAIL: network blocked";
      case EW_NET_FAULT_HTTP_TIMEOUT:     return "HTTP TIMEOUT: server slow";
      case EW_NET_FAULT_HTTP_AUTH:        return "AUTH FAIL: check API key";
      case EW_NET_FAULT_HTTP_RATE_LIMIT:  return "RATE LIMIT: retry later";
      case EW_NET_FAULT_HTTP_SERVER:      return "SERVER ERROR: retry later";
      case EW_NET_FAULT_HTTP_BAD:         return "BAD HTTP: protocol error";
      case EW_NET_FAULT_CONFIG_MISSING:   return "CONFIG MISSING: push config";
      case EW_NET_FAULT_CONFIG_INVALID:   return "CONFIG INVALID: check fields";
      case EW_NET_FAULT_API_KEY_MISSING:  return "API KEY MISSING";
      case EW_NET_FAULT_REQUEST_TOO_LONG: return "REQUEST TOO LONG";
      case EW_NET_FAULT_LLM_REPLY_BAD:    return "BAD LLM REPLY";
      case EW_NET_FAULT_RESPONSE:         return "BAD AT RESPONSE";
      case EW_NET_FAULT_BUSY:             return "BUSY: retry later";
      default:                            return "UNKNOWN NETWORK ERROR";
    }
}

int ew_net_http_status(const char *raw)
{
  const char *p;

  if (raw == NULL)
    {
      return -1;
    }

  p = strstr(raw, "HTTP/");
  if (p == NULL)
    {
      return -1;
    }
  p = strchr(p, ' ');
  if (p == NULL)
    {
      return -1;
    }
  while (*p == ' ')
    {
      p++;
    }
  if (p[0] == '\0' || p[1] == '\0' || p[2] == '\0' ||
      p[0] < '0' || p[0] > '9' ||
      p[1] < '0' || p[1] > '9' ||
      p[2] < '0' || p[2] > '9')
    {
      return -1;
    }

  return (p[0] - '0') * 100 + (p[1] - '0') * 10 + (p[2] - '0');
}

ew_net_fault_t ew_net_fault_from_http_status(int status)
{
  if (status >= 200 && status < 300)
    {
      return EW_NET_FAULT_OK;
    }
  if (status == 401 || status == 403)
    {
      return EW_NET_FAULT_HTTP_AUTH;
    }
  if (status == 429)
    {
      return EW_NET_FAULT_HTTP_RATE_LIMIT;
    }
  if (status >= 500 && status < 600)
    {
      return EW_NET_FAULT_HTTP_SERVER;
    }
  return EW_NET_FAULT_HTTP_BAD;
}

ew_net_fault_t ew_net_fault_from_join_response(const char *response)
{
  const char *p;

  if (response == NULL || response[0] == '\0')
    {
      return EW_NET_FAULT_JOIN_TIMEOUT;
    }

  p = strstr(response, "+CWJAP:");
  if (p != NULL)
    {
      p += 7;
      switch (*p)
        {
          case '1': return EW_NET_FAULT_JOIN_TIMEOUT;
          case '2': return EW_NET_FAULT_BAD_PASSWORD;
          case '3': return EW_NET_FAULT_AP_NOT_FOUND;
          case '4': return EW_NET_FAULT_JOIN_FAILED;
          default: break;
        }
    }

  if (strstr(response, "NO AP") != NULL ||
      strstr(response, "NOT FOUND") != NULL)
    {
      return EW_NET_FAULT_AP_NOT_FOUND;
    }
  if (strstr(response, "PASSWORD") != NULL ||
      strstr(response, "AUTH") != NULL)
    {
      return EW_NET_FAULT_BAD_PASSWORD;
    }
  if (strstr(response, "TIMEOUT") != NULL)
    {
      return EW_NET_FAULT_JOIN_TIMEOUT;
    }
  return EW_NET_FAULT_JOIN_FAILED;
}

int ew_net_redact_secret(const char *input, const char *secret,
                         char *output, unsigned output_size)
{
  size_t secret_len;
  unsigned used = 0;

  if (output == NULL || output_size == 0)
    {
      return -1;
    }
  output[0] = '\0';
  if (input == NULL)
    {
      return 0;
    }
  if (secret == NULL || secret[0] == '\0')
    {
      snprintf(output, output_size, "%s", input);
      return 0;
    }

  secret_len = strlen(secret);
  while (*input != '\0' && used + 1 < output_size)
    {
      if (strncmp(input, secret, secret_len) == 0)
        {
          static const char mask[] = "***";
          unsigned i;

          for (i = 0; mask[i] != '\0' && used + 1 < output_size; i++)
            {
              output[used++] = mask[i];
            }
          input += secret_len;
        }
      else
        {
          output[used++] = *input++;
        }
    }
  output[used] = '\0';
  return 0;
}
