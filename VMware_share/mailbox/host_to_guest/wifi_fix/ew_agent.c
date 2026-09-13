/****************************************************************************
 * ai_agent Skill 安装 + 主动 Tool 调度
 ****************************************************************************/

#include "ew_agent.h"
#include "ew_agent_tool.h"
#include "ew_ld2451.h"

#include <stdio.h>
#include <string.h>

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
    "# 接近提醒\n"
    "\n"
    "毫米波雷达端侧判决后，由 ai_agent 主动调用 Tool `approach_alert` 执行"
    "蜂鸣与 LCD 变色。LLM 不参与测距与门限计算。\n"
    "\n"
    "## When to use\n"
    "当 LD2451 检测到侧后靠近目标且 ew_decide 输出 SOFT/STRONG/EMERGENCY 时；"
    "或用户询问「接近预警怎么工作」「告警档位」时说明流程。\n"
    "\n"
    "## How to use\n"
    "1. 判决已在 ew_ld2451 + ew_decide 完成，禁止用 LLM 估算距离或 TTC。\n"
    "2. 主动执行 Tool `approach_alert`，参数示例：\n"
    "   `{\"level\":\"strong\",\"reason\":\"R 12.3m approaching\"}`\n"
    "3. level 取值：none | soft | strong | emergency（或 0–3）。\n"
    "4. Tool 内部只调用 alert_output(level, reason)，串口应出现 "
    "`[alert_output] level=...`。\n"
    "5. 解除告警时 level=none。\n"
    "\n"
    "## Example\n"
    "雷达 latch STRONG @ 12m → 主动 approach_alert "
    "{\"level\":\"strong\",\"reason\":\"R 12.0m approaching\"}\n"
    "→ 屏橙 WARN + 蜂鸣 + 日志 `[alert_output] level=STRONG ...`\n";

static void install_skill_file(void)
{
#ifdef __NuttX__
  char path[128];
  FILE *f;

  mkdir("/data", 0755);
  mkdir("/data/ai_agent", 0755);
  mkdir(EW_AGENT_SKILLS_DIR, 0755);

  snprintf(path, sizeof(path), "%s%s.md", EW_AGENT_SKILLS_DIR,
           EW_AGENT_SKILL_NAME);

  f = fopen(path, "r");
  if (f != NULL) {
    fclose(f);
    printf("[ew_agent] skill exists: %s\n", path);
    fflush(stdout);
    return;
  }

  f = fopen(path, "w");
  if (f == NULL) {
    printf("[ew_agent] skill write failed: %s\n", path);
    fflush(stdout);
    return;
  }
  fputs(g_approach_warn_skill, f);
  fclose(f);
  printf("[ew_agent] installed skill: %s\n", path);
  fflush(stdout);
#else
  printf("[ew_agent] stub skill install\n");
#endif
}

void ew_agent_init(void)
{
  install_skill_file();
  printf("[ew_agent] Tool approach_alert ready (calls alert_output only)\n");
  fflush(stdout);
}

int ew_agent_proactive_alert(ew_alert_level_t level, float range_m,
                             const char *reason)
{
  char ui_reason[64];
  char out[128];

  if (level != EW_ALERT_NONE && range_m > 0.0f) {
    snprintf(ui_reason, sizeof(ui_reason), "R %.1fm", range_m);
    if (reason == NULL || reason[0] == '\0') {
      reason = ui_reason;
    }
  } else if (reason == NULL) {
    reason = "";
  }

  printf("[ew_agent] proactive approach_alert level=%s range=%.1fm\n",
         ew_alert_level_name(level), range_m);
  fflush(stdout);

  return ew_agent_tool_approach_alert(level, reason, out, sizeof(out));
}
