/****************************************************************************
 * Tool approach_alert — 供 ew 主动触发与 ai_agent 注册共用
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_AGENT_TOOL_H
#define EDGE_WALKER_EW_AGENT_TOOL_H

#include "alert_output.h"

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

int tool_approach_alert_execute(const char *input_json, char *output,
                                size_t output_size);

int ew_agent_tool_approach_alert(ew_alert_level_t level, const char *reason,
                                 char *output, size_t output_size);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_AGENT_TOOL_H */
