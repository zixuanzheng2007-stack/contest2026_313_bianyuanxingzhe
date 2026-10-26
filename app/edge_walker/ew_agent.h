/****************************************************************************
 * ai_agent Skill/Tool 桥接（边缘行者 · 赛题合规）
 *
 * 雷达判决在 ew_ld2451/ew_decide（端侧，不经 LLM）。
 * 越限后由本模块主动调用 Tool approach_alert → alert_output()。
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_AGENT_H
#define EDGE_WALKER_EW_AGENT_H

#include "alert_output.h"
#include "ew_event.h"
#include "ew_ld2451.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 开机安装 approach-warn Skill、注册 Tool 元数据 */
void ew_agent_init(void);

/*
 * Single B-side entry for every pre-judged alert. Generates the event id,
 * records the source, and forwards the unchanged decision to the Tool chain.
 */
int ew_agent_emit_decision(const ew_decision_t *decision,
                           ew_event_source_t source);

/*
 * 主动触发 approach_alert Tool（LLM 不参与判距）。
 * range_m 写入 reason 副文案；返回 0 表示 Tool 执行成功。
 */
int ew_agent_proactive_alert(ew_alert_level_t level, float range_m,
                             const char *reason);

int ew_agent_proactive_alert_ex(const char *event_id,
                                ew_event_source_t source,
                                ew_alert_level_t level, float range_m,
                                const char *reason);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_AGENT_H */
