/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 提醒出口（郑子轩）
 *
 * 一次调用同时落三处：控制台一行日志、PA28 蜂鸣、屏上配色。
 * /dev/pwm0 接的是板载 LED 的 GPTIM，不是蜂鸣器，这里不再碰它。
 ****************************************************************************/

#include "alert_output.h"
#include "alert_buzzer.h"
#include "alert_lcd.h"

#include <stdio.h>

static const char *level_name(ew_alert_level_t level)
{
  switch (level) {
    case EW_ALERT_SOFT:
      return "SOFT";
    case EW_ALERT_STRONG:
      return "STRONG";
    case EW_ALERT_EMERGENCY:
      return "EMERGENCY";
    case EW_ALERT_NONE:
    default:
      return "NONE";
  }
}

void alert_output(ew_alert_level_t level, const char *reason)
{
  alert_output_event(level, reason, 0);
}

void alert_output_event(ew_alert_level_t level, const char *reason,
                        unsigned long event_id)
{
  (void)alert_output_event_checked(level, reason, event_id, false);
}

int alert_output_event_checked(ew_alert_level_t level, const char *reason,
                               unsigned long event_id, bool safety_owned)
{
  int ret;
  if (event_id != 0) {
    printf("[ew_event] event_id=%lu stage=alert_output level=%s\n",
           event_id, level_name(level));
  }
  printf("[alert_output] level=%s reason=%s\n",
         level_name(level), reason ? reason : "");
  fflush(stdout);

  ret = safety_owned ? alert_lcd_show_safety_event(level, reason, event_id) :
                       alert_lcd_show_event_checked(level, reason, event_id);
  /* A queued request is executed by the IPC consumer. Rejected requests must
   * not leave a manual buzzer running as a hidden partial side effect. */
  if (!safety_owned && ret == 0) alert_buzzer_level(level);
  return ret;
}
