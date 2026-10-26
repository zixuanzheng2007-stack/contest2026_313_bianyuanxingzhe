/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * ai_agent Tool: approach_alert
 *
 * ew 内部的本地调用；独立 ai_agent 注册入口由 ai_agent_ext 提供。
 * 只执行 alert_output(level, reason)，不读雷达、不算门限。
 ****************************************************************************/

#include "ew_agent_tool.h"
#include "alert_output.h"
#include "ew_ld2451.h"
#include "ai_agent_ext/ew_alert_ipc.h"

#include <stdio.h>
#include <string.h>

static const char *level_to_str(ew_alert_level_t level)
{
  return ew_alert_level_name(level);
}

int ew_agent_tool_execute(const char *input_json, char *output,
                                size_t output_size)
{
  ew_alert_request_t request;
  int ret = ew_alert_request_parse_json(input_json, &request);
  if (ret < 0) {
    if (output != NULL && output_size > 0) {
      snprintf(output, output_size,
               "{\"ok\":false,\"error\":\"invalid_input\"}");
    }
    return ret;
  }
  return ew_agent_tool_approach_alert_event((ew_alert_level_t)request.level,
                                           request.reason, output, output_size,
                                           request.event_id);
}

int ew_agent_tool_approach_alert(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size)
{
  return ew_agent_tool_approach_alert_event(level, reason, output, output_size, 0);
}

int ew_agent_tool_approach_alert_event(ew_alert_level_t level, const char *reason,
                                      char *output, size_t output_size,
                                      unsigned long event_id)
{
  return ew_agent_tool_dispatch_event(level, reason, output, output_size,
                                      event_id, false);
}

int ew_agent_tool_dispatch_event(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size,
                                 unsigned long event_id, bool safety_owned)
{
  int ret;
  if (level < EW_ALERT_NONE || level > EW_ALERT_EMERGENCY) {
    if (output != NULL && output_size > 0) {
      snprintf(output, output_size,
               "{\"ok\":false,\"error\":\"invalid_level\"}");
    }
    return -EINVAL;
  }
  if (event_id != 0) {
    printf("[ew_event] event_id=%lu stage=tool tool=approach_alert\n", event_id);
  }
  printf("[ai_agent] tool approach_alert level=%s reason=%s\n",
         level_to_str(level), reason ? reason : "");
  fflush(stdout);

  ret = alert_output_event_checked(level, reason ? reason : "", event_id,
                                    safety_owned);

  if (output != NULL && output_size > 0) {
    snprintf(output, output_size,
             "{\"ok\":%s,\"tool\":\"approach_alert\",\"level\":\"%s\","
             "\"event_id\":%lu,\"status\":\"%s\",\"result\":%d}",
             ret >= 0 ? "true" : "false", level_to_str(level), event_id,
             ret < 0 ? "rejected" : (ret == 1 ? "queued" : "applied"), ret);
  }
  return ret < 0 ? ret : 0;
}
