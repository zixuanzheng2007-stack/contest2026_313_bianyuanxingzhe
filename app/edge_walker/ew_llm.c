/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 读 ai_agent config.json；goldfish 先拉起 eth0，再 posix_spawn curl
 ****************************************************************************/

#include "ew_llm.h"
#include "ew_net_state.h"
#include "ew_wifi_at.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__has_include)
#  if __has_include("ew_mimo_bootstrap.h")
#    include "ew_mimo_bootstrap.h"
#  endif
#endif

#ifndef EW_MIMO_BOOTSTRAP_KEY
#define EW_MIMO_BOOTSTRAP_KEY ""
#endif

#ifdef __NuttX__
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <nuttx/config.h>
#endif

#ifndef EW_LLM_CONFIG
#define EW_LLM_CONFIG "/data/ai_agent/config/config.json"
#endif

#define EW_MIMO_HOST  "token-plan-cn.xiaomimimo.com"
#define EW_MIMO_PATH  "/v1/chat/completions"
#define EW_MIMO_PORT  "443"
#define EW_MIMO_MODEL "mimo-v2.5"

#define EW_LLM_BODY "/tmp/ew_llm_body.json"
#define EW_LLM_OUT  "/tmp/ew_llm_out.json"
#define EW_LLM_CONFIG_TMP EW_LLM_CONFIG ".tmp"
#define EW_LLM_CONFIG_BAK EW_LLM_CONFIG ".bak"

static int read_file(const char *path, char *buf, unsigned sz)
{
  FILE *fp;
  size_t n;

  fp = fopen(path, "r");
  if (fp == NULL) {
    return -1;
  }
  n = fread(buf, 1, sz - 1, fp);
  fclose(fp);
  buf[n] = '\0';
  return (int)n;
}

static int json_str(const char *json, const char *key, char *out, unsigned out_sz)
{
  const char *p;
  char pat[64];
  unsigned i;

  snprintf(pat, sizeof(pat), "\"%s\"", key);
  p = strstr(json, pat);
  if (p == NULL) {
    return -1;
  }
  p = strchr(p + strlen(pat), ':');
  if (p == NULL) {
    return -1;
  }
  p++;
  while (*p == ' ' || *p == '\t') {
    p++;
  }
  if (*p != '"') {
    return -1;
  }
  p++;
  for (i = 0; i + 1 < out_sz && *p != '\0' && *p != '"'; p++) {
    if (*p == '\\' && p[1] != '\0') {
      p++;
      out[i++] = *p;
    } else {
      out[i++] = *p;
    }
  }
  out[i] = '\0';
  return (i > 0) ? 0 : -1;
}

static void json_escape(const char *in, char *out, unsigned out_sz)
{
  unsigned o = 0;

  while (*in != '\0' && o + 2 < out_sz) {
    if (*in == '"' || *in == '\\') {
      out[o++] = '\\';
      out[o++] = *in++;
    } else if ((unsigned char)*in < 0x20) {
      in++;
    } else {
      out[o++] = *in++;
    }
  }
  out[o] = '\0';
}

#ifdef __NuttX__
static int ensure_config_dir(void)
{
  if (mkdir("/data/ai_agent", 0700) != 0 && errno != EEXIST) {
    return -1;
  }
  if (mkdir("/data/ai_agent/config", 0700) != 0 && errno != EEXIST) {
    return -1;
  }
  return 0;
}

static int copy_file(const char *src, const char *dst)
{
  FILE *in;
  FILE *out;
  char buf[256];
  size_t n;
  int rc = -1;

  in = fopen(src, "rb");
  if (in == NULL) {
    return -1;
  }
  out = fopen(dst, "wb");
  if (out == NULL) {
    fclose(in);
    return -1;
  }
  while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
    if (fwrite(buf, 1, n, out) != n) {
      goto done;
    }
  }
  if (ferror(in) == 0 && fflush(out) == 0) {
    rc = 0;
  }

done:
  fclose(out);
  fclose(in);
  if (rc != 0) {
    unlink(dst);
  }
  return rc;
}
#endif

int ew_llm_configure_mimo(const char *api_key, char *out, unsigned out_sz)
{
#ifdef __NuttX__
  FILE *fp;
  struct stat st;
  char escaped[320];

  if (out == NULL || out_sz < 8) {
    return -1;
  }
  out[0] = '\0';
  if (api_key == NULL || api_key[0] == '\0' || strlen(api_key) >= 160) {
    snprintf(out, out_sz, "invalid MiMo api_key");
    return -1;
  }
  if (ensure_config_dir() != 0) {
    snprintf(out, out_sz, "config directory failed: %d", errno);
    return -1;
  }
  json_escape(api_key, escaped, sizeof(escaped));
  fp = fopen(EW_LLM_CONFIG_TMP, "w");
  if (fp == NULL) {
    snprintf(out, out_sz, "config temp open failed: %d", errno);
    return -1;
  }
  if (fprintf(fp,
              "{\n"
              "  \"llm_host\": \"%s\",\n"
              "  \"llm_path\": \"%s\",\n"
              "  \"llm_port\": \"%s\",\n"
              "  \"model\": \"%s\",\n"
              "  \"api_key\": \"%s\"\n"
              "}\n",
              EW_MIMO_HOST, EW_MIMO_PATH, EW_MIMO_PORT, EW_MIMO_MODEL,
              escaped) < 0 || fflush(fp) != 0) {
    fclose(fp);
    unlink(EW_LLM_CONFIG_TMP);
    snprintf(out, out_sz, "config temp write failed");
    return -1;
  }
  fclose(fp);
  chmod(EW_LLM_CONFIG_TMP, 0600);

  if (stat(EW_LLM_CONFIG, &st) == 0 && stat(EW_LLM_CONFIG_BAK, &st) != 0 &&
      copy_file(EW_LLM_CONFIG, EW_LLM_CONFIG_BAK) != 0) {
    unlink(EW_LLM_CONFIG_TMP);
    snprintf(out, out_sz, "config backup failed: %d", errno);
    return -1;
  }
  if (rename(EW_LLM_CONFIG_TMP, EW_LLM_CONFIG) != 0) {
    unlink(EW_LLM_CONFIG_TMP);
    snprintf(out, out_sz, "config replace failed: %d", errno);
    return -1;
  }
  chmod(EW_LLM_CONFIG, 0600);
  snprintf(out, out_sz, "MiMo config saved (key redacted)");
  return 0;
#else
  (void)api_key;
  snprintf(out, out_sz, "host stub");
  return 0;
#endif
}

int ew_llm_restore_config(char *out, unsigned out_sz)
{
#ifdef __NuttX__
  struct stat st;

  if (out == NULL || out_sz < 8) {
    return -1;
  }
  if (stat(EW_LLM_CONFIG_BAK, &st) != 0) {
    snprintf(out, out_sz, "no config backup");
    return -1;
  }
  if (copy_file(EW_LLM_CONFIG_BAK, EW_LLM_CONFIG_TMP) != 0 ||
      rename(EW_LLM_CONFIG_TMP, EW_LLM_CONFIG) != 0) {
    unlink(EW_LLM_CONFIG_TMP);
    snprintf(out, out_sz, "config restore failed: %d", errno);
    return -1;
  }
  chmod(EW_LLM_CONFIG, 0600);
  snprintf(out, out_sz, "MiMo config restored");
  return 0;
#else
  snprintf(out, out_sz, "host stub");
  return 0;
#endif
}

static ew_llm_result_t extract_content(const char *json, char *out,
                                       unsigned out_sz)
{
  const char *choices;
  char emsg[160];

  if (strstr(json, "\"error\"") != NULL &&
      json_str(json, "message", emsg, sizeof(emsg)) == 0) {
    snprintf(out, out_sz, "LLM error: %s", emsg);
    if (strstr(emsg, "auth") != NULL || strstr(emsg, "API key") != NULL ||
        strstr(emsg, "api_key") != NULL) {
      return EW_LLM_ERR_AUTH;
    }
    return EW_LLM_ERR_RESPONSE;
  }

  choices = strstr(json, "\"choices\"");
  if (choices == NULL) {
    snprintf(out, out_sz, "bad LLM reply (no choices)");
    return EW_LLM_ERR_RESPONSE;
  }
  if (json_str(choices, "content", out, out_sz) == 0) {
    return EW_LLM_OK;
  }
  snprintf(out, out_sz, "bad LLM reply (no content)");
  return EW_LLM_ERR_RESPONSE;
}

#ifdef __NuttX__
static const char *http_body(const char *raw)
{
  const char *p;

  if (raw == NULL) {
    return NULL;
  }
  p = strstr(raw, "\r\n\r\n");
  if (p != NULL) {
    return p + 4;
  }
  p = strstr(raw, "\n\n");
  if (p != NULL) {
    return p + 2;
  }
  p = strchr(raw, '{');
  return p;
}
#endif

ew_llm_result_t ew_llm_ask(const char *prompt, char *out, unsigned out_sz)
{
#ifdef __NuttX__
  char cfg[4096];
  char host[128];
  char path[128];
  char port[16];
  char key[160];
  char model[64];
  char esc[400];
  char body[1280];
  char raw[3072];
  char runtime_key[160];
  const char *payload;
  unsigned iport;
  ew_wifi_http_result_t http_rc;
  ew_wifi_state_t wifi_state;
  int have_runtime;

  if (prompt == NULL || out == NULL || out_sz < 8) {
    return EW_LLM_ERR_INVALID;
  }
  out[0] = '\0';

  snprintf(host, sizeof(host), "%s", EW_MIMO_HOST);
  snprintf(path, sizeof(path), "%s", EW_MIMO_PATH);
  snprintf(port, sizeof(port), "%s", EW_MIMO_PORT);
  snprintf(model, sizeof(model), "%s", EW_MIMO_MODEL);
  snprintf(key, sizeof(key), "%s", EW_MIMO_BOOTSTRAP_KEY);

  have_runtime = read_file(EW_LLM_CONFIG, cfg, sizeof(cfg)) >= 0;
  runtime_key[0] = '\0';
  if (have_runtime) {
    (void)json_str(cfg, "llm_host", host, sizeof(host));
    (void)json_str(cfg, "llm_path", path, sizeof(path));
    (void)json_str(cfg, "llm_port", port, sizeof(port));
    (void)json_str(cfg, "model", model, sizeof(model));
    if (json_str(cfg, "api_key", runtime_key, sizeof(runtime_key)) == 0 &&
        runtime_key[0] != '\0') {
      snprintf(key, sizeof(key), "%s", runtime_key);
    }
  }
  if (key[0] == '\0') {
    snprintf(out, out_sz, "MiMo api_key missing (runtime and bootstrap)");
    ew_net_state_error(EW_NET_ERR_CONFIG);
    return EW_LLM_ERR_CONFIG;
  }
  printf("[ew-ask] config source=%s\n",
         have_runtime && runtime_key[0] != '\0' ? "runtime" : "bootstrap");

  wifi_state = ew_wifi_probe(0, NULL, 0);
  if (wifi_state == EW_WIFI_DOWN) {
    snprintf(out, out_sz, "ESP-AT unavailable or busy");
    ew_net_state_error(EW_NET_ERR_AT_BUSY);
    return EW_LLM_ERR_AT_BUSY;
  }
  if (wifi_state == EW_WIFI_IDLE) {
    snprintf(out, out_sz, "WiFi not connected");
    ew_net_state_error(EW_NET_ERR_NO_WIFI);
    return EW_LLM_ERR_NO_WIFI;
  }
  iport = (port[0] != '\0') ? (unsigned)atoi(port) : 443u;
  if (iport == 0) {
    iport = 443u;
  }

  json_escape(prompt, esc, sizeof(esc));
  snprintf(body, sizeof(body),
           "{\"model\":\"%s\",\"messages\":["
           "{\"role\":\"system\",\"content\":\"You are Edge Walker on openvela. "
           "Answer in Simplified Chinese if the user uses Chinese, else English. "
           "2-4 short sentences. No emoji, no markdown. "
           "Product: UART2 radar approach warning; WARN orange, CRIT red; no voice.\"},"
           "{\"role\":\"user\",\"content\":\"%s\"}]}",
           model, esc);

  printf("[ew-ask] AT SSL POST %s:%u%s\n", host, iport, path);
  http_rc = ew_wifi_http_ssl_post(host, iport, path, key, body, raw,
                                  sizeof(raw));
  if (http_rc != EW_WIFI_HTTP_OK) {
    snprintf(out, out_sz, "AT HTTP failure class=%d", (int)http_rc);
    switch (http_rc) {
      case EW_WIFI_HTTP_AT_BUSY:
      case EW_WIFI_HTTP_MODEM_DOWN:
        ew_net_state_error(EW_NET_ERR_AT_BUSY);
        return EW_LLM_ERR_AT_BUSY;
      case EW_WIFI_HTTP_TLS:
        ew_net_state_error(EW_NET_ERR_TLS);
        return EW_LLM_ERR_TLS;
      case EW_WIFI_HTTP_TIMEOUT:
        ew_net_state_error(EW_NET_ERR_TIMEOUT);
        return EW_LLM_ERR_TIMEOUT;
      default:
        ew_net_state_error(EW_NET_ERR_RESPONSE);
        return EW_LLM_ERR_RESPONSE;
    }
  }
  if (strstr(raw, "HTTP/1.1 401") != NULL ||
      strstr(raw, "HTTP/1.1 403") != NULL) {
    snprintf(out, out_sz, "MiMo authentication rejected");
    ew_net_state_error(EW_NET_ERR_AUTH);
    return EW_LLM_ERR_AUTH;
  }
  payload = http_body(raw);
  if (payload == NULL || payload[0] == '\0') {
    snprintf(out, out_sz, "empty LLM response");
    ew_net_state_error(EW_NET_ERR_RESPONSE);
    return EW_LLM_ERR_RESPONSE;
  }
  {
    ew_llm_result_t result = extract_content(payload, out, out_sz);

    if (result == EW_LLM_OK) {
      ew_net_state_error(EW_NET_ERR_NONE);
    } else if (result == EW_LLM_ERR_AUTH) {
      ew_net_state_error(EW_NET_ERR_AUTH);
    } else {
      ew_net_state_error(EW_NET_ERR_RESPONSE);
    }
    return result;
  }
#else
  snprintf(out, out_sz, "host stub: %s", prompt ? prompt : "");
  return EW_LLM_OK;
#endif
}
