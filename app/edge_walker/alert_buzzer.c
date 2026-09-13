/****************************************************************************
 * 蜂鸣器 PA28（40P.23）：无源要 2~5 kHz 方波，有源要直流高电平。
 * 板级曾把 PA28 设成 SPI1_CLK（TF），必须抢回 GPIO 并提高驱动。
 ****************************************************************************/

#include "alert_buzzer.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

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
static volatile unsigned g_alert_freq;
static int g_worker_started;
static volatile unsigned g_worker_generation;
static volatile unsigned g_worker_heartbeat;

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
  for (i = 0; i < cycles && g_alert_freq == freq_hz &&
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

  while (duration_ms > 0 && g_alert_freq == freq_hz) {
    unsigned wait_ms = duration_ms < step_ms ? duration_ms : step_ms;

    usleep(wait_ms * 1000);
    duration_ms -= wait_ms;
  }
}

static void *buzzer_worker(void *arg)
{
  unsigned generation = (unsigned)(uintptr_t)arg;
  unsigned last_freq = 0;

  (void)buzzer_claim();
  printf("[ew-buzz] worker ready gen=%u\n", generation);
  fflush(stdout);
  while (generation == g_worker_generation) {
    unsigned freq = g_alert_freq;

    g_worker_heartbeat++;
    if (freq == 0) {
      pin_off();
      usleep(10000);
      continue;
    }
    if (freq != last_freq) {
      printf("[ew-buzz] alert worker %u Hz\n", freq);
      fflush(stdout);
      last_freq = freq;
    }

    /* 开机真机已验证 400 ms 方波可响；放低优先级，不阻塞 LVGL/雷达。 */
    beep_square_alert(freq, 400, generation);
    if (g_alert_freq == freq) {
      /* 红色紧急档缩短静音；间隔可被换挡在 10 ms 内打断。 */
      alert_gap(freq, freq >= 2700 ? 40 : 120);
    }
  }
  return NULL;
}

static int buzzer_worker_start(void)
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

int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms)
{
  (void)buzzer_claim();
  printf("[ew-buzz] PA28 square+dc %u Hz\n", freq_hz);
  fflush(stdout);
  /* 有源：直流；无源：方波。两种都打，避免模块型号不明。 */
  beep_dc(180, 1);
  beep_square(freq_hz, duration_ms, 0);
  beep_square(freq_hz, 80, 1);
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

void alert_buzzer_set_alert(unsigned freq_hz)
{
  static unsigned seen_heartbeat;

  if (freq_hz == 0) {
    alert_buzzer_stop();
    return;
  }
  if (freq_hz < 2000) {
    freq_hz = 2000;
  }
  if (freq_hz > 4000) {
    freq_hz = 4000;
  }
  g_alert_freq = freq_hz;
  if (g_worker_started && g_worker_heartbeat == seen_heartbeat) {
    /* worker 已失活；换代重建，旧线程若只是迟到会自行退出。 */
    printf("[ew-buzz] worker stalled, restart\n");
    fflush(stdout);
    g_worker_started = 0;
  }
  seen_heartbeat = g_worker_heartbeat;
  if (buzzer_worker_start() != 0) {
    /* 极端低内存时至少同步打一次已验证波形。 */
    beep_square(freq_hz, 400, 0);
  }
}

void alert_buzzer_selftest(void)
{
  (void)buzzer_claim();
  printf("[ew-buzz] selftest dc then square\n");
  fflush(stdout);
  beep_dc(350, 1);
  up_udelay(80000);
  beep_square(2500, 400, 0);
  up_udelay(80000);
  beep_square(2700, 400, 1);
  pin_off();
  /* 开机即创建空闲 worker，避免首个告警才分配线程。 */
  (void)buzzer_worker_start();
}

void alert_buzzer_stop(void)
{
  g_alert_freq = 0;
  if (!g_buzzer_ready) {
    (void)buzzer_claim();
  }
  pin_off();
}

#else

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
