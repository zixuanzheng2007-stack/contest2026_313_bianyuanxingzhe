/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * ai_agent Skill 安装 + 主动 Tool 调度
 ****************************************************************************/

#include "ew_agent.h"
#include "ew_agent_tool.h"
#include "ew_ld2451.h"

#include <stdio.h>
#include <string.h>
#include <errno.h>
#ifdef __NuttX__
#include <pthread.h>
#endif

/* NuttX callers share this sequence across UI and command tasks. */
static unsigned long g_event_id;
unsigned long ew_agent_next_event_id(void)
{
  unsigned long id;
  id = __atomic_add_fetch(&g_event_id, 1ul, __ATOMIC_RELAXED);
  if (id == 0) {
    id = __atomic_add_fetch(&g_event_id, 1ul, __ATOMIC_RELAXED);
  }
  return id;
}

const char *ew_event_source_name(ew_event_source_t source)
{
  switch (source) {
    case EW_EVENT_SOURCE_RADAR: return "radar";
    case EW_EVENT_SOURCE_FAKE: return "fake";
    case EW_EVENT_SOURCE_MANUAL: return "manual";
    case EW_EVENT_SOURCE_SERIAL: return "serial";
    default: return "agent";
  }
}

#ifdef __NuttX__
#include <sys/stat.h>
#include <unistd.h>
#endif

#ifndef EW_AGENT_SKILLS_DIR
#define EW_AGENT_SKILLS_DIR "/data/ai_agent/skills/"
#endif

#ifndef EW_AGENT_SKILL_NAME
#define EW_AGENT_SKILL_NAME "approach-warn"
#endif

static const char *g_approach_warn_skill =
    "<!-- edge-walker-managed-skill:v2 -->\n"
    "# 接近提醒\n"
    "\n"
    "本 Skill 消费角色 A 已完成的端侧安全判决，不用 LLM 估算距离、TTC 或修改等级。\n"
    "\n"
    "## 何时使用\n"
    "\n"
    "- 雷达本地判决、人工告警和合成目标需要追踪或说明时。\n"
    "- NONE 是解除事件，也必须保留追踪记录。\n"
    "\n"
    "## 边界与调用\n"
    "\n"
    "1. 常驻 ew_safety 独立读取雷达、运行 ew_decide/ew_hold，并直接维护蜂鸣安全下限；切换 WARN/CHAT/WIFI 或断网不会关闭该任务。\n"
    "2. 本地主程序用 ew_agent_emit_decision 接收完整 ew_decision_t。source 是本地追踪信封：radar/fake/manual/serial/agent；event_id 是本次运行内非零数字，原 reason 不为空时保留。\n"
    "3. 本地 C Tool 调用不等于真实 packages/ai_agent registry 调用。独立 ai_agent 的 approach_alert Tool 由构建脚本注册，用 EWA1 IPC 交给主应用消费。\n"
    "4. 独立 Tool 参数只允许 level、reason、event_id。不得使用字符串 evt-* ID，也不得将本地 source 塞入此 JSON schema。\n"
    "\n"
    "```json\n"
    "{\"level\":\"strong\",\"reason\":\"strong_range_or_ttc\",\"event_id\":1001}\n"
    "```\n"
    "\n"
    "level 支持 none/soft/strong/emergency 或整数 0–3。reason 的 UTF-8 编码须少于 96 字节。\n"
    "\n"
    "## 成功与失败\n"
    "\n"
    "- 独立 Tool 的 queued 只证明请求发布；busy/invalid_input/queue_failed 都是失败。\n"
    "- 消费回调完成后写带 ID 的 applied/rejected ACK。applied 不能代替声波、屏幕像素或道路实测。\n"
    "- ACK 瞬态失败只补写结果，不重放执行器；未知锁或未落盘结果保持关闭，不能声称任意断电后 exactly-once。\n"
    "- 人工或 Agent 请求不得降低当前雷达安全等级。人工告警是持久测试模式，需在允许时用 level=none 显式解除。\n"
    "- 本地雷达事件通知是有界遥测队列；UI 阻塞时可能被标为 superseded 或丢弃并计数，不能宣称所有事件都经过独立 registry。\n"
    "\n"
    "## 无板示例与实板验收\n"
    "\n"
    "`ew fake 10 20` 产生 STRONG；`ew fake 10 2` 低于最低速度，产生 NONE。PC 对应用 `@fake 10 20`。\n"
    "\n"
    "主机测试和合成回放验证代码行为，不证明雷达方向标定、实际声音、屏幕响应或道路误报/漏报。完整板端链路仍需逐事件记录、真实观测及三次连续演示。\n";

static void install_skill_file(void)
{
#ifdef __NuttX__
  char path[128], staging[136], current[4096];
  FILE *f;
  size_t length;
  int written, closed;
  mkdir("/data", 0755);
  mkdir("/data/ai_agent", 0755);
  mkdir(EW_AGENT_SKILLS_DIR, 0755);
  snprintf(path, sizeof(path), "%s%s.md", EW_AGENT_SKILLS_DIR, EW_AGENT_SKILL_NAME);
  f = fopen(path, "rb");
  if (f != NULL) {
    uint32_t hash = 2166136261u;
    size_t i;
    length = fread(current, 1, sizeof(current), f);
    closed = ferror(f);
    fclose(f);
    if (closed || length == sizeof(current)) return;
    if (length == strlen(g_approach_warn_skill) &&
        memcmp(current, g_approach_warn_skill, length) == 0) return;
    for (i = 0; i < length; i++) hash = (hash ^ (unsigned char)current[i]) * 16777619u;
    if (!(length == 943 && hash == 3407298031u) &&
        !(length >= 31 && memcmp(current, "<!-- edge-walker-managed-skill:", 30) == 0)) {
      printf("[ew_agent] preserve custom skill: %s\n", path);
      return;
    }
  }
  snprintf(staging, sizeof(staging), "%s.tmp", path);
  f = fopen(staging, "wb");
  if (f == NULL) return;
  length = strlen(g_approach_warn_skill);
  written = fwrite(g_approach_warn_skill, 1, length, f) == length && fflush(f) == 0;
  closed = fclose(f);
  if (!written || closed != 0 || rename(staging, path) != 0) {
    unlink(staging);
    printf("[ew_agent] skill update failed: %s\n", path);
    return;
  }
  printf("[ew_agent] installed managed skill: %s\n", path);
#else
  printf("[ew_agent] stub skill install\n");
#endif
}

void ew_agent_init(void)
{
  install_skill_file();
  printf("[ew_agent] local Tool approach_alert ready (registry injection is separate)\n");
  fflush(stdout);
}

int ew_agent_proactive_alert(ew_alert_level_t level, float range_m,
                             const char *reason)
{
  ew_decision_t decision;
  memset(&decision, 0, sizeof(decision));
  decision.level = level;
  decision.range_m = range_m;
  decision.reason = reason;
  decision.ttc_s = -1.0f;
  return ew_agent_emit_decision(&decision, EW_EVENT_SOURCE_AGENT);
}

int ew_agent_emit_decision(const ew_decision_t *decision,
                           ew_event_source_t source)
{
  return ew_agent_emit_decision_event(decision, source, ew_agent_next_event_id());
}

int ew_agent_emit_decision_event(const ew_decision_t *decision,
                                 ew_event_source_t source,
                                 unsigned long event_id)
{
  char ui_reason[64];
  char out[128];
  ew_alert_level_t level;
  float range_m;
  const char *reason;
  int ret;

  if (decision == NULL || source < EW_EVENT_SOURCE_RADAR ||
      source > EW_EVENT_SOURCE_AGENT || event_id == 0) return -EINVAL;
  level = decision->level;
  range_m = decision->range_m;
  reason = decision->reason;

  if (level != EW_ALERT_NONE && range_m > 0.0f) {
    snprintf(ui_reason, sizeof(ui_reason), "R %.1fm", range_m);
    if (reason == NULL || reason[0] == '\0') {
      reason = ui_reason;
    }
  } else if (reason == NULL) {
    reason = "";
  }

  printf("[ew_event] event_id=%lu stage=decision level=%s range=%.1fm "
         "source=%s speed=%.1f ttc=%.2f\n", event_id,
         ew_alert_level_name(level), range_m, ew_event_source_name(source),
         decision->speed_kmh, decision->ttc_s);
  printf("[ew_event] event_id=%lu stage=agent dispatch=local\n", event_id);
  printf("[ew_agent] proactive approach_alert level=%s range=%.1fm\n",
         ew_alert_level_name(level), range_m);
  fflush(stdout);

  ret = ew_agent_tool_dispatch_event(level, reason, out, sizeof(out), event_id,
                                      source == EW_EVENT_SOURCE_RADAR);
  printf("[ew_event] event_id=%lu stage=complete result=%d\n", event_id, ret);
  fflush(stdout);
  return ret;
}
