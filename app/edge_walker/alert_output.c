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
  printf("[alert_output] level=%s reason=%s\n",
         level_name(level), reason ? reason : "");
  fflush(stdout);

  alert_buzzer_level(level);
  alert_lcd_show(level, reason);
}
