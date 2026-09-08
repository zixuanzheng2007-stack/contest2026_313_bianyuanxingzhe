/****************************************************************************
 * 无源蜂鸣器：PA28 软件方波（2~5 kHz）
 * 接线：VCC=40P.2(5V)  GND=40P.14  IO=40P.23(PA28)
 *
 * 串口进不了 NSH 时，靠 ew boot / rcS 自检发声，不依赖手打命令。
 * S9012 模块有的高电平有效、有的低电平有效，自检两种极性各响一拍。
 ****************************************************************************/

#include "alert_buzzer.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#ifdef __NuttX__
#include <nuttx/config.h>
#include <nuttx/arch.h>
#include "bf0_hal.h"
#endif

#ifdef __NuttX__
/* SiFli HAL 用脚号 0..31，不是 1<<n。 */
#define EW_BUZZ_PIN  ((uint16_t)28)

static int g_buzzer_ready;

static int buzzer_init(void)
{
  GPIO_InitTypeDef init;

  if (g_buzzer_ready) {
    return 0;
  }

  memset(&init, 0, sizeof(init));
  HAL_PIN_Set(PAD_PA28, GPIO_A28, PIN_NOPULL, 1);

  init.Mode = GPIO_MODE_OUTPUT;
  init.Pin = EW_BUZZ_PIN;
  init.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(hwp_gpio1, &init);
  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
  g_buzzer_ready = 1;
  return 0;
}

static int beep_polarity(unsigned freq_hz, unsigned duration_ms, int invert)
{
  unsigned half_us;
  unsigned cycles;
  unsigned i;
  GPIO_PinState on_state;
  GPIO_PinState off_state;

  if (freq_hz < 2000) {
    freq_hz = 2000;
  }
  if (freq_hz > 5000) {
    freq_hz = 5000;
  }
  if (duration_ms == 0) {
    duration_ms = 400;
  }
  if (duration_ms > 3000) {
    duration_ms = 3000;
  }

  if (buzzer_init() < 0) {
    printf("[ew-buzz] PA28 init failed\n");
    return -1;
  }

  on_state = invert ? GPIO_PIN_RESET : GPIO_PIN_SET;
  off_state = invert ? GPIO_PIN_SET : GPIO_PIN_RESET;

  half_us = 500000u / freq_hz;
  cycles = (freq_hz * duration_ms) / 1000u;
  printf("[ew-buzz] PA28 %u Hz %u ms %s (%u cycles)\n",
         freq_hz, duration_ms, invert ? "low-on" : "high-on", cycles);
  fflush(stdout);

  for (i = 0; i < cycles; i++) {
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, on_state);
    up_udelay(half_us);
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, off_state);
    up_udelay(half_us);
  }

  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
  return 0;
}

int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms)
{
  return beep_polarity(freq_hz, duration_ms, 0);
}

void alert_buzzer_selftest(void)
{
  printf("[ew-buzz] selftest high-on then low-on\n");
  fflush(stdout);
  (void)beep_polarity(2500, 450, 0);
  up_udelay(120000);
  (void)beep_polarity(2500, 450, 1);
  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
}

void alert_buzzer_stop(void)
{
  if (!g_buzzer_ready) {
    return;
  }
  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
}

#else

int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms)
{
  printf("[ew-buzz] host stub %u Hz %u ms\n", freq_hz, duration_ms);
  return 0;
}

void alert_buzzer_selftest(void)
{
  printf("[ew-buzz] host stub selftest\n");
}

void alert_buzzer_stop(void)
{
}

#endif
