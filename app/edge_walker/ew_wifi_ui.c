/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * WiFi 配网页（LVGL）
 *
 * AT 扫描要 5 s、连接要 20 s，都丢给后台线程。本文件里所有 lv_* 调用只发生在
 * build/tick/teardown，也就是 ew_ui_loop 所在的线程；后台线程只写普通变量，
 * 靠 g_job_done 交接。
 ****************************************************************************/

#include "ew_wifi_ui.h"
#include "ew_wifi_at.h"
#include "ew_chat.h"

#include <stdio.h>
#include <string.h>

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

#include <pthread.h>
#include <unistd.h>
#include <lvgl/lvgl.h>

typedef enum {
  JOB_IDLE = 0,
  JOB_STATUS,       /* 只查 CWJAP?/CIPSTA?，不探公网、不扫描 */
  JOB_SCAN,         /* 仅用户点击 Scan 时执行 */
  JOB_JOIN,
  JOB_FORGET
} ew_job_t;

static lv_obj_t *g_list;
static lv_obj_t *g_status;
static lv_obj_t *g_scan_btn;
static lv_obj_t *g_pw_layer;
static lv_obj_t *g_ssid_ta;
static lv_obj_t *g_pw_ta;
static lv_obj_t *g_pw_title;
static lv_obj_t *g_pw_kb;
static lv_obj_t *g_pw_field;
static lv_obj_t *g_pw_sw;
static int g_pw_reveal;

static ew_wifi_ap_t g_aps[EW_WIFI_SCAN_MAX];
static int g_ap_count;
static int g_scan_completed;
static char g_sel_ssid[EW_WIFI_SSID_MAX];
static char g_status_text[72];
static char g_saved_ssid[EW_WIFI_SSID_MAX];

static volatile ew_job_t g_job;
static volatile int g_job_done;
static int g_job_result;
static char g_job_pass[EW_WIFI_PASS_MAX];

static void use_font(lv_obj_t *obj)
{
  lv_font_t *f = (lv_font_t *)ew_ui_font();

  if (f != NULL) {
    lv_obj_set_style_text_font(obj, f, 0);
  }
}

static void set_dynamic_text(lv_obj_t *label, const char *text)
{
  char render_text[160];

  snprintf(render_text, sizeof(render_text), "%s", text ? text : "");
  ew_ui_sanitize_text(render_text);
  lv_label_set_text(label, render_text);
}

/****************************************************************************
 * 后台作业
 ****************************************************************************/

static void *job_thread(void *arg)
{
  ew_job_t job = g_job;

  (void)arg;

  if (job == JOB_JOIN) {
    g_job_result = ew_wifi_join(g_sel_ssid, g_job_pass, g_status_text,
                                sizeof(g_status_text));
    memset(g_job_pass, 0, sizeof(g_job_pass));
  } else if (job == JOB_FORGET) {
    g_job_result = ew_wifi_forget();
    snprintf(g_status_text, sizeof(g_status_text), "%s",
             g_job_result == 0 ? "disconnected - saved network removed"
                               : "disconnect failed - network kept");
  } else if (job == JOB_SCAN) {
    ew_wifi_ap_t scanned[EW_WIFI_SCAN_MAX];
    char ip[24];
    int n;
    ew_wifi_state_t st;

    ew_wifi_scan_hint_clear();
    if (g_saved_ssid[0] != '\0') {
      (void)ew_wifi_scan_hint_add(g_saved_ssid);
    }
    if (g_sel_ssid[0] != '\0' &&
        strcmp(g_sel_ssid, g_saved_ssid) != 0) {
      (void)ew_wifi_scan_hint_add(g_sel_ssid);
    }
    n = ew_wifi_scan(scanned, EW_WIFI_SCAN_MAX);
    if (n >= 0) {
      if (n > 0) {
        memcpy(g_aps, scanned, (size_t)n * sizeof(g_aps[0]));
      }
      g_ap_count = n;
      g_scan_completed = 1;
    }

    if (n < 0) {
      if (n == EW_WIFI_SCAN_BUSY) {
        snprintf(g_status_text, sizeof(g_status_text), "scan already running");
      } else {
        snprintf(g_status_text, sizeof(g_status_text),
                 g_ap_count > 0 ? "modem error - showing last results"
                                : "modem not responding");
      }
      g_job_done = 1;
      return NULL;
    }
    st = ew_wifi_probe(0, ip, sizeof(ip));
    if (st == EW_WIFI_DOWN && g_ap_count > 0) {
      st = EW_WIFI_IDLE;
    }

    switch (st) {
      case EW_WIFI_JOINED:
      case EW_WIFI_ONLINE:
        snprintf(g_status_text, sizeof(g_status_text), "CONNECTED  %s", ip);
        break;
      case EW_WIFI_IDLE:
        if (g_ap_count > 0) {
          snprintf(g_status_text, sizeof(g_status_text),
                   "found %d network(s)", g_ap_count);
        } else {
          snprintf(g_status_text, sizeof(g_status_text), "not connected");
        }
        break;
      default:
        if (g_ap_count > 0) {
          snprintf(g_status_text, sizeof(g_status_text),
                   "found %d network(s)", g_ap_count);
        } else {
          snprintf(g_status_text, sizeof(g_status_text), "modem not responding");
        }
        break;
    }
  } else {
    char ip[24];
    ew_wifi_state_t st = ew_wifi_probe(0, ip, sizeof(ip));

    switch (st) {
      case EW_WIFI_JOINED:
      case EW_WIFI_ONLINE:
        snprintf(g_status_text, sizeof(g_status_text), "CONNECTED  %s", ip);
        break;
      case EW_WIFI_IDLE:
        snprintf(g_status_text, sizeof(g_status_text), "not connected");
        break;
      default:
        snprintf(g_status_text, sizeof(g_status_text), "modem not responding");
        break;
    }
  }

  g_job_done = 1;
  return NULL;
}

static void job_start(ew_job_t job, const char *busy_text)
{
  pthread_t th;
  pthread_attr_t attr;

  if (g_job != JOB_IDLE) {
    return;
  }
  g_job = job;
  g_job_done = 0;
  g_job_result = -1;
  snprintf(g_status_text, sizeof(g_status_text), "%s", busy_text);
  if (g_status != NULL) {
    set_dynamic_text(g_status, g_status_text);
  }
  if (g_scan_btn != NULL) {
    lv_obj_add_state(g_scan_btn, LV_STATE_DISABLED);
  }

  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 16384);
  if (pthread_create(&th, &attr, job_thread, NULL) != 0) {
    printf("[ew-wifi-ui] job thread create failed\n");
    snprintf(g_status_text, sizeof(g_status_text), "busy, retry later");
    g_job_done = 1;
  } else {
    pthread_detach(th);
  }
  pthread_attr_destroy(&attr);
}

/****************************************************************************
 * 密码输入层
 ****************************************************************************/

static void pw_close(void)
{
  if (g_pw_layer != NULL) {
    lv_obj_add_flag(g_pw_layer, LV_OBJ_FLAG_HIDDEN);
  }
  if (g_pw_ta != NULL) {
    lv_textarea_set_text(g_pw_ta, "");
  }
  if (g_ssid_ta != NULL) {
    lv_textarea_set_text(g_ssid_ta, "");
  }
}

static void pw_cancel_cb(lv_event_t *e)
{
  (void)e;
  pw_close();
}

static void pw_connect_cb(lv_event_t *e)
{
  const char *ssid;
  const char *pass;

  (void)e;
  if (g_ssid_ta == NULL || g_pw_ta == NULL) {
    return;
  }
  ssid = lv_textarea_get_text(g_ssid_ta);
  pass = lv_textarea_get_text(g_pw_ta);
  if (ssid == NULL || ssid[0] == '\0') {
    if (g_pw_title != NULL) {
      lv_label_set_text(g_pw_title, "SSID is required");
    }
    return;
  }
  snprintf(g_sel_ssid, sizeof(g_sel_ssid), "%s", ssid);
  snprintf(g_job_pass, sizeof(g_job_pass), "%s", pass ? pass : "");
  pw_close();
  job_start(JOB_JOIN, "connecting...");
}

static void pw_reveal_cb(lv_event_t *e)
{
  lv_obj_t *sw = lv_event_get_target_obj(e);

  g_pw_reveal = lv_obj_has_state(sw, LV_STATE_CHECKED);
  if (g_pw_ta != NULL) {
    lv_textarea_set_password_mode(g_pw_ta, !g_pw_reveal);
  }
}

static void pw_field_cb(lv_event_t *e)
{
  lv_obj_t *field = lv_event_get_target_obj(e);

  g_pw_field = field;
  if (g_pw_kb != NULL) {
    lv_keyboard_set_textarea(g_pw_kb, field);
  }
  lv_obj_add_state(field, LV_STATE_FOCUSED);
}

static void pw_open(const char *ssid)
{
  int selected;

  if (g_pw_layer == NULL) {
    return;
  }
  snprintf(g_sel_ssid, sizeof(g_sel_ssid), "%s", ssid ? ssid : "");
  selected = g_sel_ssid[0] != '\0';
  if (g_pw_title != NULL) {
    if (selected) {
      char title[EW_WIFI_SSID_MAX + 16];

      snprintf(title, sizeof(title), "connect: %s", g_sel_ssid);
      set_dynamic_text(g_pw_title, title);
    } else {
      lv_label_set_text(g_pw_title, "enter hidden network");
    }
  }
  if (g_ssid_ta != NULL) {
    lv_textarea_set_text(g_ssid_ta, g_sel_ssid);
    if (selected) {
      lv_obj_add_flag(g_ssid_ta, LV_OBJ_FLAG_HIDDEN);
    } else {
      lv_obj_remove_flag(g_ssid_ta, LV_OBJ_FLAG_HIDDEN);
    }
  }
  if (g_pw_ta != NULL) {
    lv_textarea_set_text(g_pw_ta, "");
    lv_textarea_set_password_mode(g_pw_ta, !g_pw_reveal);
  }
  if (g_pw_sw != NULL) {
    if (g_pw_reveal) {
      lv_obj_add_state(g_pw_sw, LV_STATE_CHECKED);
    } else {
      lv_obj_remove_state(g_pw_sw, LV_STATE_CHECKED);
    }
  }
  if (g_pw_kb != NULL) {
    lv_obj_t *field = selected ? g_pw_ta : g_ssid_ta;

    g_pw_field = field;
    lv_keyboard_set_textarea(g_pw_kb, field);
    lv_obj_add_state(field, LV_STATE_FOCUSED);
  }
  lv_obj_remove_flag(g_pw_layer, LV_OBJ_FLAG_HIDDEN);
  lv_obj_move_foreground(g_pw_layer);
}

static void build_pw_layer(lv_obj_t *parent)
{
  lv_obj_t *card;
  lv_obj_t *row;
  lv_obj_t *btn;
  lv_obj_t *lab;
  lv_obj_t *kb;

  g_pw_layer = lv_obj_create(parent);
  lv_obj_set_size(g_pw_layer, lv_pct(100), lv_pct(100));
  lv_obj_align(g_pw_layer, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_bg_color(g_pw_layer, lv_color_hex(0x040C24), 0);
  lv_obj_set_style_bg_opa(g_pw_layer, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(g_pw_layer, 0, 0);
  lv_obj_set_style_pad_all(g_pw_layer, 8, 0);
  lv_obj_set_style_pad_left(g_pw_layer, 16, 0);
  lv_obj_set_style_pad_right(g_pw_layer, 16, 0);
  lv_obj_set_flex_flow(g_pw_layer, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(g_pw_layer, 8, 0);
  lv_obj_remove_flag(g_pw_layer, LV_OBJ_FLAG_SCROLLABLE);

  card = lv_obj_create(g_pw_layer);
  lv_obj_set_width(card, lv_pct(100));
  lv_obj_set_height(card, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_bg_opa(card, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(card, 0, 0);
  lv_obj_set_style_pad_all(card, 0, 0);
  lv_obj_set_style_pad_row(card, 6, 0);
  lv_obj_remove_flag(card, LV_OBJ_FLAG_SCROLLABLE);

  lab = lv_label_create(card);
  use_font(lab);
  lv_label_set_text(lab, "WiFi");
  lv_obj_set_style_text_color(lab, lv_color_hex(0x9FB4DC), 0);

  g_pw_title = lv_label_create(card);
  use_font(g_pw_title);
  lv_label_set_text(g_pw_title, "");
  lv_label_set_long_mode(g_pw_title, LV_LABEL_LONG_DOT);
  lv_obj_set_width(g_pw_title, lv_pct(100));
  lv_obj_set_style_text_color(g_pw_title, lv_color_white(), 0);

  g_ssid_ta = lv_textarea_create(card);
  use_font(g_ssid_ta);
  lv_obj_set_width(g_ssid_ta, lv_pct(100));
  lv_textarea_set_one_line(g_ssid_ta, true);
  lv_textarea_set_max_length(g_ssid_ta, EW_WIFI_SSID_MAX - 1);
  lv_textarea_set_placeholder_text(g_ssid_ta, "SSID / hotspot name");
  lv_obj_add_event_cb(g_ssid_ta, pw_field_cb, LV_EVENT_CLICKED, NULL);
  lv_obj_add_event_cb(g_ssid_ta, pw_field_cb, LV_EVENT_FOCUSED, NULL);

  g_pw_ta = lv_textarea_create(card);
  use_font(g_pw_ta);
  lv_obj_set_width(g_pw_ta, lv_pct(100));
  lv_textarea_set_one_line(g_pw_ta, true);
  lv_textarea_set_password_mode(g_pw_ta, true);
  lv_textarea_set_max_length(g_pw_ta, EW_WIFI_PASS_MAX - 1);
  lv_textarea_set_placeholder_text(g_pw_ta, "password (8-63 chars)");
  lv_obj_add_event_cb(g_pw_ta, pw_field_cb, LV_EVENT_CLICKED, NULL);
  lv_obj_add_event_cb(g_pw_ta, pw_field_cb, LV_EVENT_FOCUSED, NULL);

  row = lv_obj_create(card);
  lv_obj_set_width(row, lv_pct(100));
  lv_obj_set_height(row, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);
  lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(row, 0, 0);
  lv_obj_set_style_pad_all(row, 0, 0);
  lv_obj_set_style_pad_column(row, 8, 0);
  lv_obj_remove_flag(row, LV_OBJ_FLAG_SCROLLABLE);

  g_pw_sw = lv_switch_create(row);
  lv_obj_add_event_cb(g_pw_sw, pw_reveal_cb, LV_EVENT_VALUE_CHANGED, NULL);
  lab = lv_label_create(row);
  use_font(lab);
  lv_label_set_text(lab, "show");
  lv_obj_set_style_text_color(lab, lv_color_hex(0x9FB4DC), 0);

  btn = lv_button_create(row);
  lv_obj_set_size(btn, 96, 48);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x555F7A), 0);
  lab = lv_label_create(btn);
  use_font(lab);
  lv_label_set_text(lab, "cancel");
  lv_obj_center(lab);
  lv_obj_add_event_cb(btn, pw_cancel_cb, LV_EVENT_CLICKED, NULL);

  btn = lv_button_create(row);
  lv_obj_set_size(btn, 110, 48);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x2B7DE9), 0);
  lab = lv_label_create(btn);
  use_font(lab);
  lv_label_set_text(lab, "connect");
  lv_obj_center(lab);
  lv_obj_add_event_cb(btn, pw_connect_cb, LV_EVENT_CLICKED, NULL);

  g_pw_kb = lv_keyboard_create(g_pw_layer);
  kb = g_pw_kb;
  lv_obj_set_width(kb, lv_pct(100));
  lv_obj_set_flex_grow(kb, 1);
  lv_keyboard_set_textarea(kb, g_pw_ta);
  lv_obj_remove_flag(kb, LV_OBJ_FLAG_SCROLLABLE);

  lv_obj_add_flag(g_pw_layer, LV_OBJ_FLAG_HIDDEN);
}

/****************************************************************************
 * 主页面
 ****************************************************************************/

static void ap_clicked_cb(lv_event_t *e)
{
  int idx = (int)(intptr_t)lv_event_get_user_data(e);

  if (idx < 0 || idx >= g_ap_count) {
    return;
  }
  if (g_aps[idx].open) {
    snprintf(g_sel_ssid, sizeof(g_sel_ssid), "%s", g_aps[idx].ssid);
    g_job_pass[0] = '\0';
    job_start(JOB_JOIN, "connecting...");
    return;
  }
  pw_open(g_aps[idx].ssid);
}

static void scan_cb(lv_event_t *e)
{
  (void)e;
  job_start(JOB_SCAN, "scanning...");
}

static void manual_cb(lv_event_t *e)
{
  (void)e;
  pw_open("");
}

static void back_cb(lv_event_t *e)
{
  (void)e;
  ew_ui_goto(EW_PAGE_WARN);
}

static void forget_cb(lv_event_t *e)
{
  (void)e;
  job_start(JOB_FORGET, "disconnecting...");
}

static lv_obj_t *add_row_button(const char *text, lv_event_cb_t cb, void *ud)
{
  lv_obj_t *btn;
  lv_obj_t *lab;

  btn = lv_button_create(g_list);
  lv_obj_set_width(btn, lv_pct(100));
  lv_obj_set_height(btn, 44);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x0E2248), 0);
  lv_obj_set_style_pad_hor(btn, 8, 0);
  lab = lv_label_create(btn);
  use_font(lab);
  set_dynamic_text(lab, text);
  lv_label_set_long_mode(lab, LV_LABEL_LONG_DOT);
  lv_obj_set_width(lab, lv_pct(100));
  lv_obj_align(lab, LV_ALIGN_LEFT_MID, 0, 0);
  if (cb != NULL) {
    lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, ud);
  }
  return btn;
}

static void refresh_list(void)
{
  int i;
  char head[48];

  if (g_list == NULL) {
    return;
  }
  lv_obj_clean(g_list);

  if (g_ap_count == 0) {
    lv_obj_t *lab = lv_label_create(g_list);

    use_font(lab);
    if (g_job == JOB_SCAN) {
      lv_label_set_text(lab, "scanning nearby 2.4 GHz networks...");
    } else if (!g_scan_completed) {
      lv_label_set_text(lab, "tap scan to find nearby 2.4 GHz networks");
    } else {
      lv_label_set_text(lab,
                        "no 2.4 GHz network found\n"
                        "check hotspot band, then tap scan");
    }
    lv_obj_set_style_text_color(lab, lv_color_hex(0x9FB4DC), 0);
    lv_obj_set_style_pad_ver(lab, 8, 0);
    add_row_button("+ hidden network / manual SSID", manual_cb, NULL);
    return;
  }

  snprintf(head, sizeof(head), "%d network(s)", g_ap_count);
  {
    lv_obj_t *lab = lv_label_create(g_list);

    use_font(lab);
    lv_label_set_text(lab, head);
    lv_obj_set_style_text_color(lab, lv_color_hex(0x9FB4DC), 0);
    lv_obj_set_style_pad_bottom(lab, 2, 0);
  }

  for (i = 0; i < g_ap_count; i++) {
    char text[EW_WIFI_SSID_MAX + 24];

    /* 末尾的 * 表示这就是已保存的那个网络 */
    snprintf(text, sizeof(text), "%s  %ddBm%s%s",
             g_aps[i].ssid, g_aps[i].rssi,
             g_aps[i].open ? "" : "  lock",
             strcmp(g_aps[i].ssid, g_saved_ssid) == 0 ? "  *" : "");

    add_row_button(text, ap_clicked_cb, (void *)(intptr_t)i);
  }

  add_row_button("+ hidden network / manual SSID", manual_cb, NULL);
}

void ew_wifi_ui_build(void)
{
  lv_obj_t *scr;
  lv_obj_t *head;
  lv_obj_t *btn;
  lv_obj_t *lab;

  g_list = NULL;
  g_status = NULL;
  g_scan_btn = NULL;
  g_pw_layer = NULL;
  g_ssid_ta = NULL;
  g_pw_ta = NULL;
  g_pw_title = NULL;
  g_pw_kb = NULL;
  g_pw_field = NULL;
  g_pw_sw = NULL;

  if (ew_wifi_cred_load(g_saved_ssid, sizeof(g_saved_ssid), NULL, 0) != 0) {
    g_saved_ssid[0] = '\0';
  }

  scr = lv_screen_active();
  lv_obj_set_style_bg_color(scr, lv_color_hex(0x061530), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
  lv_obj_set_flex_flow(scr, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_all(scr, 8, 0);
  lv_obj_set_style_pad_row(scr, 6, 0);

  head = lv_obj_create(scr);
  lv_obj_set_width(head, lv_pct(100));
  lv_obj_set_height(head, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(head, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(head, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER,
                        LV_FLEX_ALIGN_CENTER);
  lv_obj_set_style_bg_opa(head, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(head, 0, 0);
  lv_obj_set_style_pad_all(head, 0, 0);
  lv_obj_set_style_pad_column(head, 8, 0);

  btn = lv_button_create(head);
  lv_obj_set_size(btn, EW_UI_NAV_BTN_W, EW_UI_NAV_BTN_H);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0xC45C26), 0);
  lab = lv_label_create(btn);
  use_font(lab);
  lv_label_set_text(lab, ew_ui_font() != NULL ? "预警" : "Warn");
  lv_obj_center(lab);
  lv_obj_add_event_cb(btn, back_cb, LV_EVENT_CLICKED, NULL);

  lab = lv_label_create(head);
  use_font(lab);
  lv_label_set_text(lab, "WiFi");
  lv_obj_set_style_text_color(lab, lv_color_white(), 0);
  lv_obj_set_flex_grow(lab, 1);

  g_scan_btn = lv_button_create(head);
  lv_obj_set_size(g_scan_btn, EW_UI_NAV_BTN_W, EW_UI_NAV_BTN_H);
  lv_obj_set_style_bg_color(g_scan_btn, lv_color_hex(0x2B7DE9), 0);
  lab = lv_label_create(g_scan_btn);
  use_font(lab);
  lv_label_set_text(lab, "scan");
  lv_obj_center(lab);
  lv_obj_add_event_cb(g_scan_btn, scan_cb, LV_EVENT_CLICKED, NULL);

  g_status = lv_label_create(scr);
  use_font(g_status);
  lv_label_set_long_mode(g_status, LV_LABEL_LONG_DOT);
  lv_obj_set_width(g_status, lv_pct(100));
  lv_obj_set_style_text_color(g_status, lv_color_hex(0xB8C8E8), 0);
  lv_label_set_text(g_status, "checking modem...");

  g_list = lv_obj_create(scr);
  lv_obj_set_width(g_list, lv_pct(100));
  lv_obj_set_flex_grow(g_list, 1);
  lv_obj_set_flex_flow(g_list, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(g_list, 4, 0);
  lv_obj_set_style_pad_all(g_list, 4, 0);
  lv_obj_set_scroll_dir(g_list, LV_DIR_VER);
  lv_obj_set_scrollbar_mode(g_list, LV_SCROLLBAR_MODE_AUTO);
  lv_obj_set_style_bg_color(g_list, lv_color_hex(0x06143A), 0);
  lv_obj_set_style_border_width(g_list, 0, 0);
  lv_obj_add_flag(g_list, LV_OBJ_FLAG_SCROLLABLE);

  btn = lv_button_create(scr);
  lv_obj_set_width(btn, lv_pct(100));
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x3D4F7C), 0);
  lab = lv_label_create(btn);
  use_font(lab);
  lv_label_set_text(lab, "forget saved network");
  lv_obj_center(lab);
  lv_obj_add_event_cb(btn, forget_cb, LV_EVENT_CLICKED, NULL);

  build_pw_layer(scr);
  if (g_job == JOB_IDLE) {
    job_start(JOB_STATUS, "checking connection...");
  } else {
    /* 上次离页时作业还没跑完，等它的结果落到 tick 里 */
    set_dynamic_text(g_status, g_status_text);
    lv_obj_add_state(g_scan_btn, LV_STATE_DISABLED);
  }
  refresh_list();
}

void ew_wifi_ui_tick(void)
{
  int was_join;
  int was_forget;

  if (!g_job_done) {
    return;
  }
  g_job_done = 0;
  was_join = (g_job == JOB_JOIN);
  was_forget = (g_job == JOB_FORGET);

  if (g_status != NULL) {
    set_dynamic_text(g_status, g_status_text);
  }
  if (was_join) {
    if (ew_wifi_cred_load(g_saved_ssid, sizeof(g_saved_ssid), NULL, 0) != 0) {
      g_saved_ssid[0] = '\0';
    }
  }
  if (was_forget && g_job_result == 0) {
    g_saved_ssid[0] = '\0';
  }
  g_job = JOB_IDLE;

  if (g_scan_btn != NULL) {
    lv_obj_remove_state(g_scan_btn, LV_STATE_DISABLED);
  }
  refresh_list();

  /* 连接成功后不要立刻扫描；扫描会增加延迟，旧实现还会断开刚建立的链路。 */
}

void ew_wifi_ui_teardown(void)
{
  /* 后台作业可能还在跑，这里只丢引用；对象由主循环 clean 屏幕时统一回收 */
  g_list = NULL;
  g_status = NULL;
  g_scan_btn = NULL;
  g_pw_layer = NULL;
  g_ssid_ta = NULL;
  g_pw_ta = NULL;
  g_pw_title = NULL;
  g_pw_kb = NULL;
  g_pw_field = NULL;
  g_pw_sw = NULL;
  memset(g_job_pass, 0, sizeof(g_job_pass));
}

int ew_wifi_ui_remote_set_text(const char *text)
{
  if (text == NULL || g_pw_layer == NULL || g_pw_field == NULL ||
      lv_obj_has_flag(g_pw_layer, LV_OBJ_FLAG_HIDDEN)) {
    return -1;
  }
  lv_textarea_set_text(g_pw_field, text);
  return 0;
}

int ew_wifi_ui_remote_key(const char *key)
{
  if (key == NULL || g_pw_layer == NULL || g_pw_field == NULL ||
      lv_obj_has_flag(g_pw_layer, LV_OBJ_FLAG_HIDDEN)) {
    return -1;
  }
  if (strcmp(key, "enter") == 0) {
    pw_connect_cb(NULL);
    return 0;
  }
  if (strcmp(key, "backspace") == 0) {
    lv_textarea_delete_char(g_pw_field);
    return 0;
  }
  if (strcmp(key, "escape") == 0) {
    pw_close();
    return 0;
  }
  return -1;
}

#else /* 没有 LVGL 的构建 */

void ew_wifi_ui_build(void)
{
}

void ew_wifi_ui_tick(void)
{
}

void ew_wifi_ui_teardown(void)
{
}

int ew_wifi_ui_remote_set_text(const char *text)
{
  (void)text;
  return -1;
}

int ew_wifi_ui_remote_key(const char *key)
{
  (void)key;
  return -1;
}

#endif
