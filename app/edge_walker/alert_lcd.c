/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

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
#include "ai_agent_ext/ew_alert_ipc.h"
#include "alert_buzzer.h"
#include "ew_agent.h"
#include "ew_chat.h"
#include "ew_ld2451.h"
#include "ew_safety.h"
#include "ew_wifi_at.h"
#endif

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

static pthread_t g_ui_thread;
static bool g_ui_thread_valid;
static uint32_t g_last_req_ms;
static bool g_external_active;
static ew_alert_level_t g_external_level;
static char g_external_reason[96];

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

static int queue_request(ew_alert_level_t level, const char *reason,
                          unsigned long event_id)
{
  ew_alert_request_t request = {0};
  int ret;
  request.level = (int)level;
  request.event_id = event_id;
  if (reason != NULL && strlen(reason) >= sizeof(request.reason)) {
    ret = -EMSGSIZE;
  } else {
    snprintf(request.reason, sizeof(request.reason), "%s", reason ? reason : "");
    ret = ew_alert_ipc_publish(&request);
  }
  printf("[ew_ipc] event_id=%lu stage=%s source=ew result=%d\n",
         event_id, ret == 0 ? "queued" : "rejected", ret);
  fflush(stdout);
  return ret < 0 ? ret : 1;
}

static int apply_queued_alert(const ew_alert_request_t *request, void *context)
{
  if (!g_ui_ready || g_scr == NULL || g_label == NULL) return -EAGAIN;
  /* Reject attempts to lower a live radar decision. The buzzer has the same
   * floor independently, even if the UI is stalled or showing another page. */
  {
    ew_safety_snapshot_t safety;
    ew_safety_snapshot(&safety);
    if (request->level < (int)safety.decision.level) return -EPERM;
  }
  /* Do not recurse through alert_output -> alert_lcd_show -> queue_request. */
  alert_buzzer_level((ew_alert_level_t)request->level);
  g_external_level = (ew_alert_level_t)request->level;
  snprintf(g_external_reason, sizeof(g_external_reason), "%s", request->reason);
  g_external_active = request->level != EW_ALERT_NONE;
  apply_alert_ui((ew_alert_level_t)request->level, request->reason);
  *(int *)context = 1;
  printf("[ew_ipc] event_id=%lu stage=applied level=%s\n", request->event_id,
         ew_alert_level_name((ew_alert_level_t)request->level));
  fflush(stdout);
  return 0;
}

static void poll_request(uint32_t now)
{
  ew_alert_request_t request;
  int applied = 0;
  int ret;

  if (!g_ui_ready || now - g_last_req_ms < EW_REQ_POLL_MS) {
    return;
  }
  g_last_req_ms = now;

  ret = ew_alert_ipc_consume(apply_queued_alert, &applied, &request);
  if (ret != 0) {
    printf("[ew_ipc] event_id=%lu stage=%s result=%d\n", request.event_id,
           ret == 1 ? "ack" : (applied ? "ack_failed" : "rejected"),
           ret == 1 ? 0 : ret);
    fflush(stdout);
  }
}

/****************************************************************************
 * 雷达
 ****************************************************************************/

static void render_safety(uint32_t now)
{
  ew_safety_snapshot_t safety;
  ew_safety_snapshot(&safety);
  if (!g_ui_ready) return;
  if (g_external_active && g_external_level >= safety.decision.level) {
    apply_alert_ui(g_external_level, g_external_reason);
  } else if (!safety.running) {
    apply_alert_ui(EW_ALERT_NONE, "NO RADAR");
  } else if (safety.decision.level != EW_ALERT_NONE) {
    char reason[64];
    snprintf(reason, sizeof(reason), "R %.1fm", safety.decision.range_m);
    apply_alert_ui(safety.decision.level, reason);
  } else if (safety.decision.link == EW_LINK_NOISE) {
    apply_alert_ui(EW_ALERT_NONE, "NO FRAME");
  } else if (safety.decision.link == EW_LINK_DEAD) {
    /* Silence after a valid frame cannot prove disconnection or empty road. */
    apply_alert_ui(EW_ALERT_NONE,
                   !safety.ever_bytes && now - safety.started_ms < EW_RADAR_WARMUP_MS
                   ? "RADAR WAIT" : "NO RADAR");
  } else {
    apply_alert_ui(EW_ALERT_NONE, NULL);
  }
}

void alert_lcd_service_tick(void)
{
  ew_safety_event_t event;
  ew_safety_snapshot_t current;
  unsigned count;
  uint32_t now = ew_now_ms();
  g_ui_thread = pthread_self();
  g_ui_thread_valid = true;
  /* Telemetry may lag or overflow during a blocked UI. The safety task and
   * buzzer never wait for it. Never replay old decisions as new actuations. */
  ew_safety_snapshot(&current);
  for (count = 0; count < 4 && ew_safety_take_event(&event); count++) {
    if (event.event_id != current.event_id) {
      printf("[ew_event] event_id=%lu stage=superseded source=radar\n",
             event.event_id);
    } else {
      (void)ew_agent_emit_decision_event(&event.decision,
                                         EW_EVENT_SOURCE_RADAR, event.event_id);
    }
  }
  poll_request(now);
  render_safety(now);
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

  render_safety(now);
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
  alert_lcd_show_event(level, reason, 0);
}

void alert_lcd_show_event(ew_alert_level_t level, const char *reason,
                          unsigned long event_id)
{
  (void)alert_lcd_show_event_checked(level, reason, event_id);
}

int alert_lcd_show_event_checked(ew_alert_level_t level, const char *reason,
                                 unsigned long event_id)
{
  ew_safety_snapshot_t safety;
  ew_safety_snapshot(&safety);
  if (level < safety.decision.level) return -EPERM;
  if (g_ui_ready && g_ui_thread_valid && pthread_equal(pthread_self(), g_ui_thread)) {
    if (reason != NULL && strlen(reason) >= sizeof(g_external_reason)) return -EMSGSIZE;
    g_external_level = level;
    snprintf(g_external_reason, sizeof(g_external_reason), "%s", reason ? reason : "");
    g_external_active = level != EW_ALERT_NONE;
    apply_alert_ui(level, reason);
    if (event_id != 0) {
      printf("[ew_event] event_id=%lu stage=actuator actuator=lcd\n", event_id);
      fflush(stdout);
    }
    return 0;
  }
  return queue_request(level, reason, event_id);
}

int alert_lcd_show_safety_event(ew_alert_level_t level, const char *reason,
                                unsigned long event_id)
{
  (void)level; (void)reason; (void)event_id;
  if (!g_ui_thread_valid || !pthread_equal(pthread_self(), g_ui_thread)) return -EPERM;
  render_safety(ew_now_ms());
  return g_ui_ready ? 0 : 1;
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
  alert_lcd_show_event(level, reason, 0);
}

void alert_lcd_show_event(ew_alert_level_t level, const char *reason,
                          unsigned long event_id)
{
  (void)event_id;
  printf("[alert_lcd] stub level=%d reason=%s\n",
         (int)level, reason ? reason : "");
}

int alert_lcd_show_event_checked(ew_alert_level_t level, const char *reason,
                                 unsigned long event_id)
{
  alert_lcd_show_event(level, reason, event_id);
  return 0;
}
int alert_lcd_show_safety_event(ew_alert_level_t level, const char *reason,
                                unsigned long event_id)
{
  return alert_lcd_show_event_checked(level, reason, event_id);
}
void alert_lcd_service_tick(void) {}

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
