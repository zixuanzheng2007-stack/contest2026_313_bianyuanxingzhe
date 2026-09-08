/****************************************************************************
 * 提醒出口实现（郑子轩）
 *
 * 1) 控制台一定打印一行（NSH / 串口能看见）
 * 2) 板上若有 /dev/pwm0，则按档位开蜂鸣；没有则跳过，不算失败
 * 3) PA28 无源蜂鸣器软件方波（DevKit-LCD 40P.23）
 * 4) 可选刷新 LCD 色块（alert_lcd）
 ****************************************************************************/

#include "alert_output.h"
#include "alert_lcd.h"
#include "alert_buzzer.h"

#include <stdint.h>
#include <stdio.h>

#ifdef __NuttX__
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <errno.h>
#ifdef CONFIG_PWM
#include <nuttx/timers/pwm.h>
#endif
#endif

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

#ifdef __NuttX__
#ifdef CONFIG_PWM
static void pwm_apply(ew_alert_level_t level)
{
  struct pwm_info_s info;
  int fd = open("/dev/pwm0", O_RDWR);
  if (fd < 0) {
    return;
  }

  if (level == EW_ALERT_NONE) {
    ioctl(fd, PWMIOC_STOP, 0);
    close(fd);
    return;
  }

  if (level == EW_ALERT_EMERGENCY) {
    info.frequency = 2800;
    info.duty = (uint32_t)(0.7f * 65536.0f);
  } else if (level == EW_ALERT_STRONG) {
    info.frequency = 2200;
    info.duty = (uint32_t)(0.5f * 65536.0f);
  } else {
    info.frequency = 1600;
    info.duty = (uint32_t)(0.3f * 65536.0f);
  }

#ifdef CONFIG_PWM_NCHANNELS
  info.channels[0].channel = 1;
  info.channels[0].duty = info.duty;
#endif

  if (ioctl(fd, PWMIOC_SETCHARACTERISTICS, (unsigned long)((uintptr_t)&info)) >= 0) {
    ioctl(fd, PWMIOC_START, 0);
  }
  close(fd);
}
#else
static void pwm_apply(ew_alert_level_t level)
{
  (void)level;
}
#endif
#endif

void alert_output(ew_alert_level_t level, const char *reason)
{
  printf("[alert_output] level=%s reason=%s\n",
         level_name(level),
         reason ? reason : "");
  fflush(stdout);

#ifdef __NuttX__
  pwm_apply(level);
  if (level == EW_ALERT_NONE) {
    alert_buzzer_stop();
  } else if (level == EW_ALERT_EMERGENCY) {
    alert_buzzer_beep(2500, 500);
  } else if (level == EW_ALERT_STRONG) {
    alert_buzzer_beep(2200, 400);
  } else {
    alert_buzzer_beep(1800, 350);
  }
#endif
  alert_lcd_show(level, reason);
}
