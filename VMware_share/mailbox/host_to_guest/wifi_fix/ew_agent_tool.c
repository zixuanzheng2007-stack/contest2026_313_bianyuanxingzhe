/****************************************************************************
 * ai_agent Tool: approach_alert
 *
 * 对齐 packages/ai_agent tool_registry 的 execute 签名。
 * 本 Tool 只做一件事：alert_output(level, reason)。不读雷达、不算门限。
 ****************************************************************************/

#include "ew_agent_tool.h"
#include "alert_output.h"
#include "ew_ld2451.h"

#include <stdio.h>
#include <string.h>

static const char *level_to_str(ew_alert_level_t level)
{
  return ew_alert_level_name(level);
}

static ew_alert_level_t level_from_str(const char *s)
{
  if (s == NULL || s[0] == '\0') {
    return EW_ALERT_NONE;
  }
  if (strcmp(s, "none") == 0 || strcmp(s, "NONE") == 0 ||
      strcmp(s, "0") == 0) {
    return EW_ALERT_NONE;
  }
  if (strcmp(s, "soft") == 0 || strcmp(s, "SOFT") == 0 ||
      strcmp(s, "1") == 0) {
    return EW_ALERT_SOFT;
  }
  if (strcmp(s, "strong") == 0 || strcmp(s, "STRONG") == 0 ||
      strcmp(s, "2") == 0) {
    return EW_ALERT_STRONG;
  }
  if (strcmp(s, "emergency") == 0 || strcmp(s, "EMERGENCY") == 0 ||
      strcmp(s, "crit") == 0 || strcmp(s, "CRIT") == 0 ||
      strcmp(s, "3") == 0) {
    return EW_ALERT_EMERGENCY;
  }
  return EW_ALERT_SOFT;
}

/* 极简 JSON 解析：{"level":"strong","reason":"..."} */
static int parse_input(const char *input_json, ew_alert_level_t *level_out,
                       char *reason_out, unsigned reason_sz)
{
  const char *p;
  char level_buf[16];

  if (level_out == NULL) {
    return -1;
  }
  *level_out = EW_ALERT_SOFT;
  if (reason_out != NULL && reason_sz > 0) {
    reason_out[0] = '\0';
  }

  if (input_json == NULL || input_json[0] == '\0') {
    return 0;
  }

  p = strstr(input_json, "\"level\"");
  if (p != NULL) {
    p = strchr(p, ':');
    if (p != NULL) {
      p++;
      while (*p == ' ' || *p == '\t') {
        p++;
      }
      if (*p == '"') {
        unsigned i = 0;

        p++;
        while (*p != '\0' && *p != '"' && i + 1 < sizeof(level_buf)) {
          level_buf[i++] = *p++;
        }
        level_buf[i] = '\0';
        *level_out = level_from_str(level_buf);
      }
    }
  }

  if (reason_out == NULL || reason_sz == 0) {
    return 0;
  }

  p = strstr(input_json, "\"reason\"");
  if (p == NULL) {
    return 0;
  }
  p = strchr(p, ':');
  if (p == NULL) {
    return 0;
  }
  p++;
  while (*p == ' ' || *p == '\t') {
    p++;
  }
  if (*p != '"') {
    return 0;
  }
  p++;
  {
    unsigned o = 0;

    while (*p != '\0' && *p != '"' && o + 1 < reason_sz) {
      if (*p == '\\' && p[1] != '\0') {
        p++;
      }
      reason_out[o++] = *p++;
    }
    reason_out[o] = '\0';
  }
  return 0;
}

int tool_approach_alert_execute(const char *input_json, char *output,
                              size_t output_size)
{
  ew_alert_level_t level = EW_ALERT_SOFT;
  char reason[96];

  parse_input(input_json, &level, reason, sizeof(reason));
  return ew_agent_tool_approach_alert(level, reason, output, output_size);
}

int ew_agent_tool_approach_alert(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size)
{
  printf("[ai_agent] tool approach_alert level=%s reason=%s\n",
         level_to_str(level), reason ? reason : "");
  fflush(stdout);

  alert_output(level, reason ? reason : "");

  if (output != NULL && output_size > 0) {
    snprintf(output, output_size,
             "{\"ok\":true,\"tool\":\"approach_alert\",\"level\":\"%s\","
             "\"reason\":\"%s\"}",
             level_to_str(level), reason ? reason : "");
  }
  return 0;
}
