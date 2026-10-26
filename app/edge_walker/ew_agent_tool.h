/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * Tool approach_alert — ew 本地执行入口（独立注册使用 IPC 实现）
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_AGENT_TOOL_H
#define EDGE_WALKER_EW_AGENT_TOOL_H

#include "alert_output.h"

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Keep the local JSON executor distinct from ai_agent's IPC tool symbol in
 * NuttX flat builds, where both applications share the same final image. */
int ew_agent_tool_execute(const char *input_json, char *output,
                                size_t output_size);

int ew_agent_tool_approach_alert(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size);

int ew_agent_tool_approach_alert_event(ew_alert_level_t level, const char *reason,
                                      char *output, size_t output_size,
                                      unsigned long event_id);

/* Radar sound is already owned by the independent safety task; delivery must
 * not turn a delayed radar observation into a persistent manual buzzer request. */
int ew_agent_tool_dispatch_event(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size,
                                 unsigned long event_id, bool safety_owned);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_AGENT_TOOL_H */
