/* SPDX-License-Identifier: Apache-2.0 */
/* ai_agent publishes one request; only the ew UI consumer reports applied. */
#include "ew_alert_ipc.h"
#include "tool_approach_alert.h"

static const char *level_name(int level)
{
  static const char *const names[] = {"NONE", "SOFT", "STRONG", "EMERGENCY"};
  return level >= 0 && level <= 3 ? names[level] : "INVALID";
}

int tool_approach_alert_execute(const char *input_json, char *output,
                                size_t output_size)
{
  ew_alert_request_t request = {0};
  int ret = ew_alert_request_parse_json(input_json, &request);
  const char *error = "invalid_input";
  if (ret == 0) {
    ret = ew_alert_ipc_publish(&request);
    error = ret == -EBUSY ? "busy" : "queue_failed";
  }
  if (ret < 0) {
    printf("[ew_ipc] event_id=%lu stage=rejected error=%s result=%d\n",
           request.event_id, error, ret);
    if (output != NULL && output_size > 0)
      snprintf(output, output_size,
               "{\"ok\":false,\"error\":\"%s\",\"result\":%d}", error, ret);
  } else {
    printf("[ew_ipc] event_id=%lu stage=queued level=%s\n",
           request.event_id, level_name(request.level));
    if (output != NULL && output_size > 0)
      snprintf(output, output_size,
               "{\"ok\":true,\"status\":\"queued\",\"event_id\":%lu,"
               "\"level\":\"%s\"}", request.event_id, level_name(request.level));
  }
  fflush(stdout);
  return ret;
}
