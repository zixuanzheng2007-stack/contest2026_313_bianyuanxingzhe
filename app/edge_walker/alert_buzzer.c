/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 蜂鸣器 PA28（40P.23）：无源要 2~5 kHz 方波，有源要直流高电平。
 * 板级曾把 PA28 设成 SPI1_CLK（TF），必须抢回 GPIO 并提高驱动。
 ****************************************************************************/

#include "alert_buzzer.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>

#ifdef __NuttX__
#include <nuttx/config.h>
#include <nuttx/arch.h>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include "bf0_hal.h"
#endif

#ifdef __NuttX__
#define EW_BUZZ_PIN  ((uint16_t)28)

static int g_buzzer_ready;
static unsigned g_alert_freq;
static pthread_mutex_t g_control_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned g_safety_freq;
static int g_worker_started;
static volatile unsigned g_worker_generation;
static volatile unsigned g_worker_heartbeat;

static unsigned active_freq(void)
{
  unsigned floor = __atomic_load_n(&g_safety_freq, __ATOMIC_RELAXED);
  unsigned manual = __atomic_load_n(&g_alert_freq, __ATOMIC_RELAXED);
  return manual > floor ? manual : floor;
}

static int buzzer_claim(void)
{
  GPIO_InitTypeDef init;

  memset(&init, 0, sizeof(init));
  HAL_PIN_Set(PAD_PA28, GPIO_A28, PIN_NOPULL, 1);
  HAL_PIN_Set_DS0(PAD_PA28, 1, 1);
  HAL_PIN_Set_DS1(PAD_PA28, 1, 1);

  init.Mode = GPIO_MODE_OUTPUT;
  init.Pin = EW_BUZZ_PIN;
  init.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(hwp_gpio1, &init);
  g_buzzer_ready = 1;
  return 0;
}

static void pin_off(void)
{
  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
}

static void beep_dc(unsigned duration_ms, int high)
{
  unsigned i;

  if (duration_ms < 80) {
    duration_ms = 80;
  }
  if (duration_ms > 800) {
    duration_ms = 800;
  }
  HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN,
                    high ? GPIO_PIN_SET : GPIO_PIN_RESET);
  for (i = 0; i < duration_ms; i++) {
    up_udelay(1000);
  }
  pin_off();
}

static void beep_square(unsigned freq_hz, unsigned duration_ms, int invert)
{
  unsigned half_us;
  unsigned cycles;
  unsigned i;
  GPIO_PinState on_state;
  GPIO_PinState off_state;

  if (freq_hz < 2000) {
    freq_hz = 2000;
  }
  if (freq_hz > 4000) {
    freq_hz = 4000;
  }
  if (duration_ms < 120) {
    duration_ms = 120;
  }
  if (duration_ms > 600) {
    duration_ms = 600;
  }

  on_state = invert ? GPIO_PIN_RESET : GPIO_PIN_SET;
  off_state = invert ? GPIO_PIN_SET : GPIO_PIN_RESET;
  half_us = 500000u / freq_hz;
  cycles = (freq_hz * duration_ms) / 1000u;

  for (i = 0; i < cycles; i++) {
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, on_state);
    up_udelay(half_us);
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, off_state);
    up_udelay(half_us);
  }
  pin_off();
}

static void beep_square_alert(unsigned freq_hz, unsigned duration_ms,
                              unsigned generation)
{
  unsigned half_us;
  unsigned cycles;
  unsigned i;

  if (freq_hz < 2000) {
    freq_hz = 2000;
  }
  if (freq_hz > 4000) {
    freq_hz = 4000;
  }
  half_us = 500000u / freq_hz;
  cycles = (freq_hz * duration_ms) / 1000u;

  /* 换挡时立即退出旧频率，别让屏幕先变级、声音最多晚 400 ms。 */
  for (i = 0; i < cycles && active_freq() == freq_hz &&
                  generation == g_worker_generation; i++) {
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_SET);
    up_udelay(half_us);
    HAL_GPIO_WritePin(hwp_gpio1, EW_BUZZ_PIN, GPIO_PIN_RESET);
    up_udelay(half_us);
    g_worker_heartbeat++;
  }
  pin_off();
}

static void alert_gap(unsigned freq_hz, unsigned duration_ms)
{
  const unsigned step_ms = 10;

  while (duration_ms > 0 && active_freq() == freq_hz) {
    unsigned wait_ms = duration_ms < step_ms ? duration_ms : step_ms;

    usleep(wait_ms * 1000);
    duration_ms -= wait_ms;
  }
}

static void *buzzer_worker(void *arg)
{
  unsigned generation = (unsigned)(uintptr_t)arg;

  (void)buzzer_claim();
  while (generation == g_worker_generation) {
    unsigned freq = active_freq();

    g_worker_heartbeat++;
    if (freq == 0) {
      pin_off();
      usleep(10000);
      continue;
    }
    /* 开机真机已验证 400 ms 方波可响；放低优先级，不阻塞 LVGL/雷达。 */
    beep_square_alert(freq, 400, generation);
    if (active_freq() == freq) {
      /* 红色紧急档缩短静音；间隔可被换挡在 10 ms 内打断。 */
      alert_gap(freq, freq >= 2700 ? 40 : 120);
    }
  }
  return NULL;
}

static int buzzer_worker_start_unlocked(void)
{
  pthread_t th;
  pthread_attr_t attr;
  struct sched_param param;
  int ret;

  if (g_worker_started) {
    return 0;
  }
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 8192);
  pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);
  memset(&param, 0, sizeof(param));
  param.sched_priority = 80;
  pthread_attr_setschedparam(&attr, &param);
  g_worker_generation++;
  ret = pthread_create(&th, &attr, buzzer_worker,
                       (void *)(uintptr_t)g_worker_generation);
  pthread_attr_destroy(&attr);
  if (ret != 0) {
    printf("[ew-buzz] worker create failed=%d\n", ret);
    fflush(stdout);
    return ret;
  }
  pthread_detach(th);
  g_worker_started = 1;
  return 0;
}

static int buzzer_worker_start(void)
{
  int ret;
  pthread_mutex_lock(&g_control_lock);
  ret = buzzer_worker_start_unlocked();
  pthread_mutex_unlock(&g_control_lock);
  return ret;
}

int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms)
{
  pthread_mutex_lock(&g_control_lock);
  if (g_worker_started || __atomic_load_n(&g_safety_freq, __ATOMIC_RELAXED) != 0) {
    pthread_mutex_unlock(&g_control_lock);
    return -EBUSY;
  }
  (void)buzzer_claim();
  printf("[ew-buzz] PA28 square+dc %u Hz\n", freq_hz);
  fflush(stdout);
  /* 有源：直流；无源：方波。两种都打，避免模块型号不明。 */
  beep_dc(180, 1);
  beep_square(freq_hz, duration_ms, 0);
  beep_square(freq_hz, 80, 1);
  pthread_mutex_unlock(&g_control_lock);
  return 0;
}

void alert_buzzer_level(ew_alert_level_t level)
{
  switch (level) {
    case EW_ALERT_EMERGENCY:
      alert_buzzer_set_alert(2700);
      break;
    case EW_ALERT_STRONG:
      alert_buzzer_set_alert(2500);
      break;
    case EW_ALERT_SOFT:
      alert_buzzer_set_alert(2300);
      break;
    default:
      alert_buzzer_set_alert(0);
      break;
  }
}

int alert_buzzer_prepare(void)
{
  int ret;
  pthread_mutex_lock(&g_control_lock);
  if (!g_buzzer_ready) (void)buzzer_claim();
  ret = buzzer_worker_start_unlocked();
  pthread_mutex_unlock(&g_control_lock);
  return ret;
}

void alert_buzzer_safety_level(ew_alert_level_t level)
{
  unsigned frequency = level == EW_ALERT_EMERGENCY ? 2700u :
                       level == EW_ALERT_STRONG ? 2500u :
                       level == EW_ALERT_SOFT ? 2300u : 0u;
  __atomic_store_n(&g_safety_freq, frequency, __ATOMIC_RELAXED);
}

void alert_buzzer_set_alert(unsigned freq_hz)
{
  if (freq_hz == 0) {
    alert_buzzer_stop();
    return;
  }
  if (freq_hz < 2000) freq_hz = 2000;
  if (freq_hz > 4000) freq_hz = 4000;
  __atomic_store_n(&g_alert_freq, freq_hz, __ATOMIC_RELAXED);
  /* Startup is serialized. Calling twice before a waveform heartbeat is not
   * evidence that the existing worker is stalled and must be replaced. */
  (void)buzzer_worker_start();
}

void alert_buzzer_selftest(void)
{
  pthread_mutex_lock(&g_control_lock);
  if (g_worker_started || __atomic_load_n(&g_safety_freq, __ATOMIC_RELAXED) != 0) {
    pthread_mutex_unlock(&g_control_lock);
    return;
  }
  (void)buzzer_claim();
  printf("[ew-buzz] selftest dc then square\n");
  fflush(stdout);
  beep_dc(350, 1);
  up_udelay(80000);
  beep_square(2500, 400, 0);
  up_udelay(80000);
  beep_square(2700, 400, 1);
  pin_off();
  /* Once this worker starts, it is the only GPIO waveform owner. */
  (void)buzzer_worker_start_unlocked();
  pthread_mutex_unlock(&g_control_lock);
}

void alert_buzzer_stop(void)
{
  __atomic_store_n(&g_alert_freq, 0u, __ATOMIC_RELAXED);
  if (!g_buzzer_ready) {
    (void)buzzer_claim();
  }
  if (active_freq() == 0) pin_off();
}

#else

int alert_buzzer_prepare(void) { return 0; }
void alert_buzzer_safety_level(ew_alert_level_t level) { (void)level; }

int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms)
{
  printf("[ew-buzz] host stub %u Hz %u ms\n", freq_hz, duration_ms);
  return 0;
}

void alert_buzzer_level(ew_alert_level_t level)
{
  printf("[ew-buzz] host stub level=%d\n", (int)level);
}

void alert_buzzer_set_alert(unsigned freq_hz)
{
  printf("[ew-buzz] host stub alert %u Hz\n", freq_hz);
}

void alert_buzzer_selftest(void)
{
  printf("[ew-buzz] host stub selftest\n");
}

void alert_buzzer_stop(void)
{
}

#endif
