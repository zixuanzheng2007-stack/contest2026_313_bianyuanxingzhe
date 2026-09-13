/****************************************************************************
 * 读 ai_agent config.json；goldfish 先拉起 eth0，再 posix_spawn curl
 ****************************************************************************/

#include "ew_llm.h"
#include "ew_wifi_at.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __NuttX__
#include <unistd.h>
#include <sys/stat.h>
#include <nuttx/config.h>
#endif

#ifndef EW_LLM_CONFIG
#define EW_LLM_CONFIG "/data/ai_agent/config/config.json"
#endif

#define EW_LLM_BODY "/tmp/ew_llm_body.json"
#define EW_LLM_OUT  "/tmp/ew_llm_out.json"

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

static int extract_content(const char *json, char *out, unsigned out_sz)
{
  const char *choices;
  char emsg[160];

  if (strstr(json, "\"error\"") != NULL &&
      json_str(json, "message", emsg, sizeof(emsg)) == 0) {
    snprintf(out, out_sz, "LLM error: %s", emsg);
    return -1;
  }

  choices = strstr(json, "\"choices\"");
  if (choices == NULL) {
    snprintf(out, out_sz, "bad LLM reply (no choices)");
    return -1;
  }
  if (json_str(choices, "content", out, out_sz) == 0) {
    return 0;
  }
  snprintf(out, out_sz, "bad LLM reply (no content)");
  return -1;
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

int ew_llm_ask(const char *prompt, char *out, unsigned out_sz)
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
  const char *payload;
  unsigned iport;
  int rc;

  if (prompt == NULL || out == NULL || out_sz < 8) {
    return -1;
  }
  out[0] = '\0';

  if (read_file(EW_LLM_CONFIG, cfg, sizeof(cfg)) < 0) {
    snprintf(out, out_sz, "missing %s (adb push MiMo config)", EW_LLM_CONFIG);
    return -1;
  }

  host[0] = path[0] = port[0] = key[0] = model[0] = '\0';
  json_str(cfg, "llm_host", host, sizeof(host));
  json_str(cfg, "llm_path", path, sizeof(path));
  json_str(cfg, "llm_port", port, sizeof(port));
  json_str(cfg, "api_key", key, sizeof(key));
  json_str(cfg, "model", model, sizeof(model));
  if (host[0] == '\0' || key[0] == '\0') {
    snprintf(out, out_sz, "config.json missing llm_host/api_key");
    return -1;
  }
  if (path[0] == '\0') {
    strncpy(path, "/v1/chat/completions", sizeof(path) - 1);
  }
  if (model[0] == '\0') {
    strncpy(model, "mimo-v2.5", sizeof(model) - 1);
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
  rc = ew_wifi_http_ssl_post(host, iport, path, key, body, raw, sizeof(raw));
  if (rc != 0) {
    snprintf(out, out_sz, "AT HTTP fail (mod no IP/SSL/CIPSEND)");
    return -1;
  }
  payload = http_body(raw);
  if (payload == NULL || payload[0] == '\0') {
    snprintf(out, out_sz, "empty LLM response");
    return -1;
  }
  return extract_content(payload, out, out_sz);
#else
  snprintf(out, out_sz, "host stub: %s", prompt ? prompt : "");
  return 0;
#endif
}
