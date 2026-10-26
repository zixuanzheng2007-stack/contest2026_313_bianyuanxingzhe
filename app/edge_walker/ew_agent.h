/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * ai_agent Skill/Tool 桥接（边缘行者 · 赛题合规）
 *
 * 雷达判决在 ew_ld2451/ew_decide（端侧，不经 LLM）。
 * 越限后由本模块主动调用 Tool approach_alert → alert_output()。
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_AGENT_H
#define EDGE_WALKER_EW_AGENT_H

#include "alert_output.h"
#include "ew_ld2451.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 开机安装 approach-warn Skill；独立 ai_agent 注册由构建脚本注入。 */
void ew_agent_init(void);

/* Selected Stage1 idea: trace metadata stays separate from A's decision.
 * Numeric IDs and EWA1 IPC stay compatible with the hardened implementation. */
typedef enum {
  EW_EVENT_SOURCE_RADAR, EW_EVENT_SOURCE_FAKE, EW_EVENT_SOURCE_MANUAL,
  EW_EVENT_SOURCE_SERIAL, EW_EVENT_SOURCE_AGENT
} ew_event_source_t;
const char *ew_event_source_name(ew_event_source_t source);
unsigned long ew_agent_next_event_id(void);
int ew_agent_emit_decision(const ew_decision_t *decision,
                           ew_event_source_t source);
int ew_agent_emit_decision_event(const ew_decision_t *decision,
                                 ew_event_source_t source,
                                 unsigned long event_id);

/*
 * 主动触发 approach_alert Tool（LLM 不参与判距）。
 * range_m 写入 reason 副文案；返回 0 表示 Tool 执行成功。
 */
int ew_agent_proactive_alert(ew_alert_level_t level, float range_m,
                             const char *reason);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_AGENT_H */
