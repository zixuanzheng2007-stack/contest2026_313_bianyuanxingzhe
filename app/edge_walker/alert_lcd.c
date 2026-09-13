/****************************************************************************
 * 预警页：LVGL on /dev/lcd0
 *
 * 显示只有 LVGL 一条路径。曾经的 /dev/fb0 整屏填色会和 LVGL 抢同一块显存，
 * 已经全部移除。
 ****************************************************************************/

#include "alert_lcd.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>

#ifdef __NuttX__
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <sys/boardctl.h>
#include <nuttx/config.h>
#ifdef CONFIG_LV_USE_NUTTX
#include <lvgl/lvgl.h>
#endif
#include "alert_buzzer.h"
#include "ew_agent.h"
#include "ew_chat.h"
#include "ew_ld2451.h"
#include "ew_wifi_at.h"
#endif

/* 非 UI 进程（NSH 里的 ew alert ...）把请求丢在这里，常驻 UI 下一拍取走 */
#define EW_ALERT_REQ "/data/ew_alert.req"

/* 取请求文件的间隔：这条路径只服务人工调试，不值得每帧 open 一次 */
#define EW_REQ_POLL_MS 200u

/* 串口打开后给雷达首帧留时间，避免启动瞬间误报断线。 */
#define EW_RADAR_WARMUP_MS 3000u

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

static lv_obj_t *g_scr;
static lv_obj_t *g_label;
static lv_obj_t *g_reason_label;
static lv_obj_t *g_net_label;
static bool g_ui_ready;
static uint32_t g_display_bg = UINT32_MAX;

static int g_radar_fd = -1;
static ew_hold_t g_hold;
static ew_sniff_stats_t g_sniff;
static bool g_hold_inited;
static uint32_t g_radar_started_ms;
static ew_alert_level_t g_buzz_level = EW_ALERT_NONE;
static uint32_t g_buzz_level_ms;
static uint32_t g_last_req_ms;

/* 告警期间每隔这么久重发一次挡位，作为后台 worker 的心跳补偿 */
#ifndef EW_BUZZ_REPEAT_MS
#define EW_BUZZ_REPEAT_MS 700u
#endif

static char g_wifi_status[EW_WIFI_STAT_MAX];
static volatile int g_wifi_status_dirty;
static int g_wifi_started;

static uint32_t ew_now_ms(void)
{
  static uint32_t fallback_ms;
  struct timespec ts;

  if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
    return (uint32_t)((uint64_t)ts.tv_sec * 1000u +
                      (uint64_t)ts.tv_nsec / 1000000u);
  }
  /* 时钟读不到也必须单调递增，否则 hold 的超时判定会整个失效 */
  fallback_ms += 20u;
  return fallback_ms;
}

/****************************************************************************
 * 画面
 ****************************************************************************/

static void apply_alert_ui(ew_alert_level_t level, const char *reason)
{
  uint32_t bg;
  const char *main_text;

  if (!g_ui_ready || g_scr == NULL || g_label == NULL) {
    return;
  }

  switch (level) {
    case EW_ALERT_EMERGENCY:
      bg = 0xFF0000u;
      main_text = "CRIT";
      break;
    case EW_ALERT_STRONG:
      bg = 0xFF8C00u;
      main_text = "WARN";
      break;
    case EW_ALERT_SOFT:
      bg = 0xC9A227u;
      main_text = "SOFT";
      break;
    default:
      if (reason != NULL && strcmp(reason, "RADAR WAIT") == 0) {
        bg = 0x082060u;
        main_text = "RADAR...";
      } else if (reason != NULL && strcmp(reason, "NO RADAR") == 0) {
        bg = 0x3A3A3Au;
        main_text = "NO RADAR";
      } else if (reason != NULL && strcmp(reason, "NO FRAME") == 0) {
        bg = 0x4A3A20u;
        main_text = "NO FRAME";
      } else {
        bg = 0x082060u;
        main_text = "EW READY";
      }
      reason = NULL;   /* 无告警时正文已经说明了状态 */
      break;
  }

  if (bg != g_display_bg) {
    printf("[alert_lcd] display level=%s rgb=%06lx text=%s reason=%s\n",
           ew_alert_level_name(level), (unsigned long)bg, main_text,
           reason ? reason : "");
    fflush(stdout);
    g_display_bg = bg;
  }
  lv_obj_set_style_bg_color(g_scr, lv_color_hex(bg), 0);
  lv_obj_set_style_bg_opa(g_scr, LV_OPA_COVER, 0);
  lv_label_set_text(g_label, main_text);
  lv_obj_center(g_label);

  if (g_reason_label == NULL) {
    return;
  }
  if (reason != NULL && reason[0] != '\0') {
    lv_label_set_text(g_reason_label, reason);
    lv_obj_remove_flag(g_reason_label, LV_OBJ_FLAG_HIDDEN);
    lv_obj_align_to(g_reason_label, g_label, LV_ALIGN_OUT_BOTTOM_MID, 0, 8);
  } else {
    lv_obj_add_flag(g_reason_label, LV_OBJ_FLAG_HIDDEN);
  }
}

/****************************************************************************
 * 跨进程告警请求
 ****************************************************************************/

static void queue_request(ew_alert_level_t level, const char *reason)
{
  char line[96];
  int fd;

  snprintf(line, sizeof(line), "%d %s\n", (int)level, reason ? reason : "");
  fd = open(EW_ALERT_REQ, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0) {
    printf("[alert_lcd] queue open failed errno=%d\n", errno);
    fflush(stdout);
    return;
  }
  (void)write(fd, line, strlen(line));
  close(fd);
}

static void poll_request(uint32_t now)
{
  char line[96];
  char reason[64];
  const char *sp;
  ssize_t n;
  int level_i;
  int fd;

  if (now - g_last_req_ms < EW_REQ_POLL_MS) {
    return;
  }
  g_last_req_ms = now;

  fd = open(EW_ALERT_REQ, O_RDONLY);
  if (fd < 0) {
    return;
  }
  n = read(fd, line, sizeof(line) - 1);
  close(fd);
  unlink(EW_ALERT_REQ);
  if (n <= 0) {
    return;
  }

  line[n] = '\0';
  level_i = (int)EW_ALERT_NONE;
  reason[0] = '\0';
  if (sscanf(line, "%d %63[^\n]", &level_i, reason) < 1) {
    return;
  }
  sp = reason;
  while (*sp == ' ') {
    sp++;
  }
  apply_alert_ui((ew_alert_level_t)level_i, sp);
}

/****************************************************************************
 * 雷达
 ****************************************************************************/

static void apply_decision(const ew_decision_t *d, uint32_t now)
{
  char ui_reason[32];
  int fire;

  if (d->level != EW_ALERT_NONE) {
    snprintf(ui_reason, sizeof(ui_reason), "R %.1fm", d->range_m);
    apply_alert_ui(d->level, ui_reason);
  } else if (d->link == EW_LINK_DEAD) {
    if (g_hold.ever_frame) {
      /*
       * LD2451 在无目标后可能停止上报；没有独立心跳时，静默不能等同
       * 于拔线。既然本次启动已收到过有效帧，就按正常空闲显示。
       */
      apply_alert_ui(EW_ALERT_NONE, NULL);
    } else if (g_hold.ever_bytes) {
      apply_alert_ui(EW_ALERT_NONE, "NO FRAME");
    } else if ((now - g_radar_started_ms) < EW_RADAR_WARMUP_MS) {
      apply_alert_ui(EW_ALERT_NONE, "RADAR WAIT");
    } else {
      apply_alert_ui(EW_ALERT_NONE, "NO RADAR");
    }
  } else if (d->link == EW_LINK_NOISE) {
    apply_alert_ui(EW_ALERT_NONE, "NO FRAME");
  } else {
    apply_alert_ui(EW_ALERT_NONE, NULL);
  }

  /* 换挡必发；告警持续时按心跳重发，万一 worker 没起来还能补一次波形 */
  fire = (d->level != g_buzz_level) ||
         (d->level != EW_ALERT_NONE &&
          (now - g_buzz_level_ms) >= EW_BUZZ_REPEAT_MS);
  if (fire) {
    printf("[alert_lcd] latch %s -> %s range=%.1fm speed=%.1fkm/h "
           "ttc=%.2fs %s link=%d\n",
           ew_alert_level_name(g_buzz_level), ew_alert_level_name(d->level),
           d->range_m, d->speed_kmh, d->ttc_s,
           d->reason ? d->reason : "", (int)d->link);
    fflush(stdout);
    if (d->level != g_buzz_level) {
      ew_agent_proactive_alert(d->level, d->range_m, d->reason);
    } else {
      alert_buzzer_level(d->level);
    }
    g_buzz_level = d->level;
    g_buzz_level_ms = now;
  }
}

static void poll_radar(uint32_t now)
{
  uint8_t buf[64];
  ew_track_t track;
  ew_decision_t d;
  const ew_track_t *tp = NULL;
  bool had_bytes = false;
  bool had_frame = false;

  if (!g_hold_inited) {
    ew_hold_reset(&g_hold);
    memset(&g_sniff, 0, sizeof(g_sniff));
    g_radar_started_ms = now;
    g_hold_inited = true;
  }

  if (g_radar_fd < 0) {
    g_radar_fd = open(EW_RADAR_DEV, O_RDONLY | O_NONBLOCK);
  } else {
    memset(&track, 0, sizeof(track));
    for (;;) {
      ew_sniff_stats_t before = g_sniff;
      ssize_t n = read(g_radar_fd, buf, sizeof(buf));

      if (n <= 0) {
        break;
      }
      had_bytes = true;
      if (ew_ld2451_feed_sniff(buf, (unsigned)n, &g_sniff, &track) &&
          track.valid) {
        tp = &track;
      }
      if (g_sniff.frames_ok > before.frames_ok) {
        had_frame = true;
      }
    }
  }

  d = ew_hold_update(&g_hold, now, had_bytes, had_frame, tp);
  apply_decision(&d, now);
}

/****************************************************************************
 * 开机联网（后台线程，别挡住预警刷新）
 ****************************************************************************/

static void *wifi_boot_thread(void *arg)
{
  int i;

  (void)arg;
  /* 模组不在时 at_wake 已经把各个波特率都试过了，这里不必再多轮重试 */
  for (i = 0; i < 2; i++) {
    int rc = ew_wifi_bringup(g_wifi_status, sizeof(g_wifi_status));

    g_wifi_status_dirty = 1;
    if (rc == 0) {
      break;
    }
    sleep(3);
  }
  return NULL;
}

static void wifi_boot_start(void)
{
  pthread_t th;
  pthread_attr_t attr;

  if (g_wifi_started) {
    return;
  }
  g_wifi_started = 1;
  snprintf(g_wifi_status, sizeof(g_wifi_status), "WiFi...");
  g_wifi_status_dirty = 1;

  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 16384);
  if (pthread_create(&th, &attr, wifi_boot_thread, NULL) != 0) {
    printf("[alert_lcd] wifi thread failed, skip auto join\n");
    fflush(stdout);
    snprintf(g_wifi_status, sizeof(g_wifi_status), "WiFi ?");
    g_wifi_status_dirty = 1;
  } else {
    pthread_detach(th);
  }
  pthread_attr_destroy(&attr);
}

static void wifi_status_refresh(void)
{
  if (!g_wifi_status_dirty || g_net_label == NULL) {
    return;
  }
  g_wifi_status_dirty = 0;
  lv_label_set_text(g_net_label, g_wifi_status);
}

/****************************************************************************
 * 页面
 ****************************************************************************/

static void goto_chat_cb(lv_event_t *e)
{
  (void)e;
  ew_ui_goto(EW_PAGE_CHAT);
}

static void goto_wifi_cb(lv_event_t *e)
{
  (void)e;
  ew_ui_goto(EW_PAGE_WIFI);
}

static lv_obj_t *make_button(lv_obj_t *parent, const char *text, uint32_t color,
                             lv_align_t align, int32_t x, int32_t y,
                             lv_event_cb_t cb)
{
  lv_obj_t *btn = lv_button_create(parent);
  lv_obj_t *lab = lv_label_create(btn);

  lv_obj_set_size(btn, EW_UI_NAV_BTN_W, EW_UI_NAV_BTN_H);
  lv_obj_align(btn, align, x, y);
  lv_obj_set_style_bg_color(btn, lv_color_hex(color), 0);
  lv_label_set_text(lab, text);
  lv_obj_center(lab);
  lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, NULL);
  return btn;
}

void alert_lcd_attach_warn_ui(void)
{
  g_scr = lv_screen_active();
  lv_obj_clean(g_scr);
  lv_obj_set_layout(g_scr, LV_LAYOUT_NONE);
  lv_obj_set_style_pad_all(g_scr, 0, 0);

  g_label = lv_label_create(g_scr);
  lv_obj_set_style_text_color(g_label, lv_color_white(), 0);

  g_reason_label = lv_label_create(g_scr);
  lv_obj_set_style_text_color(g_reason_label, lv_color_white(), 0);
  lv_obj_add_flag(g_reason_label, LV_OBJ_FLAG_HIDDEN);

  /* 网络状态点一下就进配网页 */
  g_net_label = lv_label_create(g_scr);
  lv_label_set_text(g_net_label, g_wifi_status[0] ? g_wifi_status : "WiFi...");
  lv_obj_set_style_text_color(g_net_label, lv_color_hex(0xD0E0FF), 0);
  lv_obj_align(g_net_label, LV_ALIGN_TOP_LEFT, 8, 10);
  lv_obj_add_flag(g_net_label, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(g_net_label, goto_wifi_cb, LV_EVENT_CLICKED, NULL);

  (void)make_button(g_scr, "Agent", 0x2B7DE9, LV_ALIGN_TOP_RIGHT, -8, 8,
                    goto_chat_cb);
  (void)make_button(g_scr, "WiFi", 0x2E7D5B, LV_ALIGN_BOTTOM_RIGHT, -8, -8,
                    goto_wifi_cb);

  g_ui_ready = true;
  wifi_boot_start();
  apply_alert_ui(EW_ALERT_NONE, NULL);
}

void alert_lcd_warn_tick(void)
{
  uint32_t now = ew_now_ms();

  poll_request(now);
  poll_radar(now);
  wifi_status_refresh();
}

void alert_lcd_detach_warn_ui(void)
{
  g_ui_ready = false;
  g_scr = NULL;
  g_label = NULL;
  g_reason_label = NULL;
  g_net_label = NULL;
}

void alert_lcd_show(ew_alert_level_t level, const char *reason)
{
  if (g_ui_ready) {
    apply_alert_ui(level, reason);
    return;
  }
  /* 常驻 UI 不在本进程（NSH 里手动敲的 ew alert），落盘交给它 */
  queue_request(level, reason);
}

int alert_lcd_info(void)
{
  lv_display_t *disp = lv_display_get_default();

  if (disp == NULL) {
    printf("[alert_lcd] LVGL display not ready\n");
    return 1;
  }
  printf("[alert_lcd] lvgl %dx%d\n",
         (int)lv_display_get_horizontal_resolution(disp),
         (int)lv_display_get_vertical_resolution(disp));
  return 0;
}

int alert_lcd_selftest(void)
{
  if (!g_ui_ready) {
    printf("[alert_lcd] warn page not attached (run from `ew boot`)\n");
    return 1;
  }
  apply_alert_ui(EW_ALERT_EMERGENCY, NULL);
  usleep(500000);
  apply_alert_ui(EW_ALERT_SOFT, NULL);
  usleep(500000);
  apply_alert_ui(EW_ALERT_NONE, NULL);
  printf("[alert_lcd] selftest red -> yellow -> blue\n");
  return 0;
}

void alert_lcd_boot_splash(void)
{
  lv_nuttx_dsc_t info;
  lv_nuttx_result_t result;
  int lcdfd;
  int ret;

  g_scr = NULL;
  g_label = NULL;
  g_reason_label = NULL;
  g_ui_ready = false;

  printf("[ew-boot] splash enter\n");
  fflush(stdout);

  if (lv_is_initialized()) {
    printf("[ew-boot] ERR lvgl already initialized, abort\n");
    fflush(stdout);
    return;
  }

  ret = boardctl(BOARDIOC_INIT, 0);
  printf("[ew-boot] boardctl ret=%d\n", ret);
  fflush(stdout);
  usleep(200000);

  lcdfd = open("/dev/lcd0", O_RDWR);
  printf("[ew-boot] lcd0 fd=%d errno=%d\n", lcdfd, lcdfd < 0 ? errno : 0);
  fflush(stdout);
  if (lcdfd >= 0) {
    close(lcdfd);
  }

  lv_init();
  lv_nuttx_dsc_init(&info);
#ifdef CONFIG_LV_USE_NUTTX_LCD
  info.fb_path = "/dev/lcd0";
#endif
#ifdef CONFIG_INPUT_TOUCHSCREEN
  info.input_path = "/dev/input0";
#endif
  lv_nuttx_init(&info, &result);
  if (result.disp == NULL) {
    printf("[ew-boot] ERR lv_nuttx_init disp=NULL\n");
    fflush(stdout);
    return;
  }

  printf("[ew-boot] display up, enter UI loop\n");
  fflush(stdout);
  alert_buzzer_selftest();
  ew_ui_loop(0);
}

#else /* 没有 LVGL 的构建（host smoke / 仿真） */

void alert_lcd_show(ew_alert_level_t level, const char *reason)
{
  printf("[alert_lcd] stub level=%d reason=%s\n",
         (int)level, reason ? reason : "");
}

void alert_lcd_boot_splash(void)
{
  printf("[alert_lcd] stub: no LVGL in this build\n");
}

void alert_lcd_attach_warn_ui(void)
{
}

void alert_lcd_warn_tick(void)
{
}

void alert_lcd_detach_warn_ui(void)
{
}

int alert_lcd_selftest(void)
{
  printf("[alert_lcd] stub selftest\n");
  return 0;
}

int alert_lcd_info(void)
{
  printf("[alert_lcd] stub info\n");
  return 0;
}

#endif
