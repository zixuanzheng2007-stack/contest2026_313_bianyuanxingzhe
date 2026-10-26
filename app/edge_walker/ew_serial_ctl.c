/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 读 /dev/console 上以 @ 开头的行；UI 占线时 PC 仍可遥控。
 ****************************************************************************/

#include "ew_serial_ctl.h"
#include "ew_mirror.h"
#include "alert_output.h"
#include "ew_chat.h"
#include "ew_agent.h"
#include "ew_ld2451.h"
#include "ew_llm.h"
#include "ew_wifi_at.h"
#include "ew_snapshot.h"
#include "ew_radar_diag.h"

#include <ctype.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifdef __NuttX__
#include <poll.h>
#include <nuttx/config.h>
#ifdef CONFIG_LV_USE_NUTTX
#include <lvgl/lvgl.h>
#endif
#endif

#define EW_CTL_LINE_MAX 768
#define EW_CTL_Q_MAX    16

typedef struct {
  char lines[EW_CTL_Q_MAX][EW_CTL_LINE_MAX];
  int head;
  int tail;
  pthread_mutex_t mu;
} ew_ctl_queue_t;

static ew_ctl_queue_t g_q;
static int g_reader_started;

static void q_push(const char *line)
{
  pthread_mutex_lock(&g_q.mu);
  if (((g_q.tail + 1) % EW_CTL_Q_MAX) != g_q.head) {
    snprintf(g_q.lines[g_q.tail], EW_CTL_LINE_MAX, "%s", line);
    g_q.tail = (g_q.tail + 1) % EW_CTL_Q_MAX;
  } else {
    if (strncmp(line, "mimo-set", 8) == 0) {
      printf("[ew-ctl] queue full, drop: mimo-set ***\n");
    } else if (strncmp(line, "join", 4) == 0) {
      printf("[ew-ctl] queue full, drop: join ***\n");
    } else if (strncmp(line, "input", 5) == 0 ||
               strncmp(line, "submit", 6) == 0) {
      printf("[ew-ctl] queue full, drop: remote text ***\n");
    } else {
      printf("[ew-ctl] queue full, drop: %s\n", line);
    }
  }
  pthread_mutex_unlock(&g_q.mu);
}

static int q_pop(char *out, unsigned out_sz)
{
  int got = 0;

  pthread_mutex_lock(&g_q.mu);
  if (g_q.head != g_q.tail) {
    snprintf(out, out_sz, "%s", g_q.lines[g_q.head]);
    g_q.head = (g_q.head + 1) % EW_CTL_Q_MAX;
    got = 1;
  }
  pthread_mutex_unlock(&g_q.mu);
  return got;
}

static void skip_spaces(const char **p)
{
  while (**p != '\0' && isspace((unsigned char)**p)) {
    (*p)++;
  }
}

static void parse_token(const char **p, char *tok, unsigned tok_sz)
{
  unsigned n = 0;

  skip_spaces(p);
  if (**p == '"') {
    (*p)++;
    while (**p != '\0' && **p != '"' && n + 1 < tok_sz) {
      tok[n++] = **p;
      (*p)++;
    }
    if (**p == '"') {
      (*p)++;
    }
  } else {
    while (**p != '\0' && !isspace((unsigned char)**p) && n + 1 < tok_sz) {
      tok[n++] = **p;
      (*p)++;
    }
  }
  tok[n] = '\0';
}

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

static lv_obj_t *g_touch_obj;
static lv_obj_t *g_touch_scroll;
static lv_point_t g_touch_start;
static lv_point_t g_touch_last;
static int g_touch_moved;

static lv_obj_t *ctl_hit_obj(lv_obj_t *root, lv_point_t *pt)
{
  lv_obj_t *child;
  uint32_t i;
  uint32_t n;

  if (root == NULL || lv_obj_has_flag(root, LV_OBJ_FLAG_HIDDEN)) {
    return NULL;
  }
  n = lv_obj_get_child_count(root);
  for (i = n; i > 0; i--) {
    child = lv_obj_get_child(root, i - 1);
    child = ctl_hit_obj(child, pt);
    if (child != NULL) {
      return child;
    }
  }
  if (lv_obj_hit_test(root, pt)) {
    return root;
  }
  return NULL;
}

static lv_obj_t *ctl_scroll_parent(lv_obj_t *obj)
{
  while (obj != NULL) {
    if (lv_obj_has_flag(obj, LV_OBJ_FLAG_SCROLLABLE)) {
      return obj;
    }
    obj = lv_obj_get_parent(obj);
  }
  return NULL;
}

static lv_obj_t *ctl_click_target(lv_obj_t *obj)
{
  lv_obj_t *hit = obj;
  lv_obj_t *clickable = NULL;

  while (obj != NULL) {
    if (lv_obj_check_type(obj, &lv_button_class)) {
      return obj;
    }
    if (clickable == NULL && lv_obj_has_flag(obj, LV_OBJ_FLAG_CLICKABLE)) {
      clickable = obj;
    }
    obj = lv_obj_get_parent(obj);
  }
  return clickable != NULL ? clickable : hit;
}

static void ctl_touch_down(int16_t x, int16_t y)
{
  lv_point_t pt;

  pt.x = x;
  pt.y = y;
  g_touch_obj = ctl_click_target(ctl_hit_obj(lv_screen_active(), &pt));
  if (g_touch_obj == NULL) {
    printf("[ew-ctl] touch down %d,%d: no widget\n", (int)x, (int)y);
    return;
  }
  g_touch_scroll = ctl_scroll_parent(g_touch_obj);
  g_touch_start = pt;
  g_touch_last = pt;
  g_touch_moved = 0;
  lv_obj_send_event(g_touch_obj, LV_EVENT_PRESSED, NULL);
}

static void ctl_touch_move(int16_t x, int16_t y)
{
  int dx;
  int dy;

  if (g_touch_obj == NULL) {
    return;
  }
  dx = (int)x - (int)g_touch_last.x;
  dy = (int)y - (int)g_touch_last.y;
  if (abs((int)x - (int)g_touch_start.x) > 5 ||
      abs((int)y - (int)g_touch_start.y) > 5) {
    g_touch_moved = 1;
  }
  if (g_touch_scroll != NULL && (dx != 0 || dy != 0)) {
    lv_obj_scroll_by(g_touch_scroll, -dx, -dy, LV_ANIM_OFF);
  }
  g_touch_last.x = x;
  g_touch_last.y = y;
  lv_obj_send_event(g_touch_obj, LV_EVENT_PRESSING, NULL);
}

static void ctl_touch_up(int16_t x, int16_t y)
{
  if (g_touch_obj == NULL) {
    return;
  }
  if (!g_touch_moved) {
    lv_obj_send_event(g_touch_obj, LV_EVENT_CLICKED, NULL);
  }
  lv_obj_send_event(g_touch_obj, LV_EVENT_RELEASED, NULL);
  printf("[ew-ctl] touch %d,%d -> %d,%d moved=%d obj=%p\n",
         (int)g_touch_start.x, (int)g_touch_start.y, (int)x, (int)y,
         g_touch_moved, (void *)g_touch_obj);
  g_touch_obj = NULL;
  g_touch_scroll = NULL;
  g_touch_moved = 0;
}

static void ctl_tap(int16_t x, int16_t y)
{
  ctl_touch_down(x, y);
  ctl_touch_up(x, y);
}

static void ctl_goto_page(const char *name)
{
  if (strcmp(name, "warn") == 0 || strcmp(name, "alert") == 0 ||
      strcmp(name, "0") == 0) {
    ew_ui_goto(EW_PAGE_WARN);
  } else if (strcmp(name, "chat") == 0 || strcmp(name, "agent") == 0 ||
             strcmp(name, "1") == 0) {
    ew_ui_goto(EW_PAGE_CHAT);
  } else if (strcmp(name, "wifi") == 0 || strcmp(name, "2") == 0) {
    ew_ui_goto(EW_PAGE_WIFI);
  } else {
    printf("[ew-ctl] goto ? use warn|wifi|chat\n");
    return;
  }
  printf("[ew-ctl] goto %s\n", name);
}

static ew_alert_level_t ctl_alert_level(const char *tok)
{
  if (strcmp(tok, "none") == 0 || strcmp(tok, "0") == 0) {
    return EW_ALERT_NONE;
  }
  if (strcmp(tok, "strong") == 0 || strcmp(tok, "2") == 0 ||
      strcmp(tok, "warn") == 0) {
    return EW_ALERT_STRONG;
  }
  if (strcmp(tok, "crit") == 0 || strcmp(tok, "3") == 0 ||
      strcmp(tok, "emergency") == 0) {
    return EW_ALERT_EMERGENCY;
  }
  if (strcmp(tok, "soft") == 0 || strcmp(tok, "1") == 0) return EW_ALERT_SOFT;
  return (ew_alert_level_t)-1;
}

static void ctl_fake(float range_m, float speed)
{
  ew_track_t t;
  ew_decision_t d;

  memset(&t, 0, sizeof(t));
  t.valid = true;
  t.range_m = range_m;
  t.speed_kmh = speed;
  t.snr = 30.0f;
  t.approaching = (speed > 0.0f);
  t.ttc_s = t.approaching ? (t.range_m / (t.speed_kmh / 3.6f)) : -1.0f;
  d = ew_decide(&t);
  printf("[ew-ctl] fake %.1fm %.1fkm/h -> %s\n", range_m, speed, d.reason);
  (void)ew_agent_emit_decision(&d, EW_EVENT_SOURCE_SERIAL);
}

static void *ctl_worker(void *arg)
{
  char *line = (char *)arg;
  const char *p = line;
  char verb[32];

  parse_token(&p, verb, sizeof(verb));

  if (strcmp(verb, "scan") == 0) {
    ew_wifi_ap_t aps[EW_WIFI_SCAN_MAX];
    int n = ew_wifi_scan(aps, EW_WIFI_SCAN_MAX);
    int i;

    if (n < 0) {
      printf("[ew-ctl] scan %s\n",
             n == EW_WIFI_SCAN_BUSY ? "already running" : "failed");
    } else {
      for (i = 0; i < n; i++) {
        printf("  %-32s %4d dBm  %s\n", aps[i].ssid, aps[i].rssi,
               aps[i].open ? "open" : "locked");
      }
      printf("[ew-ctl] scan %d network(s)\n", n);
    }
  } else if (strcmp(verb, "join") == 0) {
    char ssid[EW_WIFI_SSID_MAX];
    char pass[EW_WIFI_PASS_MAX];
    char status[EW_WIFI_STAT_MAX];

    parse_token(&p, ssid, sizeof(ssid));
    parse_token(&p, pass, sizeof(pass));
    if (ssid[0] == '\0') {
      printf("[ew-ctl] join needs SSID\n");
    } else if (ew_wifi_join(ssid, pass, status, sizeof(status)) != 0) {
      printf("[ew-ctl] join fail: %s\n", status);
    } else {
      printf("[ew-ctl] join ok: %s\n", status);
    }
  } else if (strcmp(verb, "forget") == 0) {
    int rc = ew_wifi_forget();

    printf("[ew-ctl] forget %s rc=%d\n", rc == 0 ? "ok" : "fail", rc);
  } else if (strcmp(verb, "ask") == 0) {
    char reply[512];
    char question[EW_CTL_LINE_MAX];

    skip_spaces(&p);
    snprintf(question, sizeof(question), "%s", p);
    if (question[0] == '\0') {
      snprintf(question, sizeof(question), "你好");
    }
    if (ew_llm_ask(question, reply, sizeof(reply)) != 0) {
      printf("[ew-ctl] ask fail: %s\n", reply);
    } else {
      printf("[ew-ctl] ask ok: %s\n", reply);
    }
  } else {
    printf("[ew-ctl] worker unknown: %s\n", verb);
  }

  free(line);
  return NULL;
}

static void ctl_spawn_worker(const char *line)
{
  char *copy;
  pthread_t tid;
  pthread_attr_t attr;

  copy = strdup(line);
  if (copy == NULL) {
    return;
  }
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 65536);
  if (pthread_create(&tid, &attr, ctl_worker, copy) != 0) {
    printf("[ew-ctl] worker spawn failed\n");
    free(copy);
  } else {
    pthread_detach(tid);
  }
  pthread_attr_destroy(&attr);
}

static void ctl_radar_diag(const char *request_id)
{
  ew_safety_snapshot_t snapshot;
  char message[EW_RADAR_DIAG_MAX_BYTES];

  /* Only the existing safety owner reads radar bytes. This console handler
   * copies its state, then formats outside the snapshot lock. */
  ew_safety_snapshot(&snapshot);
  if (ew_radar_diag_format(message, sizeof(message), request_id, &snapshot) < 0) {
    printf("[ew-radar-diag] {\"v\":1,\"id\":null,\"error\":{\"code\":\"invalid_request\"}}\n");
  } else {
    printf("[ew-radar-diag] %s\n", message);
  }
  fflush(stdout);
}

static void ctl_snapshot(const char *request_id)
{
  static unsigned long sequence;
  ew_safety_snapshot_t snapshot;
  char message[512];

  /* Existing UI/command consumer only. The safety task never formats or
   * writes console data, and copying its snapshot performs no AT operation. */
  ew_safety_snapshot(&snapshot);
  sequence++;
  if (sequence == 0) {
    sequence++;
  }
  if (ew_snapshot_format(message, sizeof(message), request_id, &snapshot,
                         sequence) < 0) {
    printf("[ew-snapshot] {\"v\":1,\"id\":null,\"error\":{\"code\":\"invalid_request\"}}\n");
  } else {
    printf("[ew-snapshot] %s\n", message);
  }
  fflush(stdout);
}

static void ctl_dispatch(const char *line)
{
  const char *p = line;
  char verb[32];
  char a[32];
  char b[32];
  char c[32];

  parse_token(&p, verb, sizeof(verb));
  if (verb[0] == '\0') {
    return;
  }

  if (strcmp(verb, "sensitivity") == 0) {
    char id[64];
    char setting[32];
    unsigned i;
    int valid = 1;
    parse_token(&p, id, sizeof(id));
    parse_token(&p, setting, sizeof(setting));
    skip_spaces(&p);
    if (*p != '\0' || id[0] == '\0' || strlen(id) > 48) valid = 0;
    for (i = 0; id[i]; i++) {
      unsigned char v = (unsigned char)id[i];
      if (!((v >= 'a' && v <= 'z') || (v >= 'A' && v <= 'Z') ||
            (v >= '0' && v <= '9') || v == '_' || v == '-')) valid = 0;
    }
    if (strcmp(setting, "get") != 0 && strcmp(setting, "standard") != 0 &&
        strcmp(setting, "early") != 0) valid = 0;
    if (!valid) {
      printf("[ew-sensitivity] {\"v\":1,\"id\":null,\"ok\":false}\n");
    } else {
      if (strcmp(setting, "get") != 0) {
        (void)ew_sensitivity_set(strcmp(setting, "early") == 0
                                 ? EW_SENSITIVITY_EARLY : EW_SENSITIVITY_STANDARD);
      }
      printf("[ew-sensitivity] {\"v\":1,\"id\":\"%s\",\"ok\":true,"
             "\"profile\":\"%s\",\"factor\":%.2f,\"volatile\":true}\n",
             id, ew_sensitivity_get() == EW_SENSITIVITY_EARLY ? "early" : "standard",
             ew_sensitivity_get() == EW_SENSITIVITY_EARLY ? 1.25 : 1.0);
    }
    fflush(stdout);
    return;
  }

  if (strcmp(verb, "snapshot") == 0) {
    /* Validate the full ID, without parse_token's silent truncation. */
    skip_spaces(&p);
    ctl_snapshot(p);
    return;
  }

  if (strcmp(verb, "radar-diag") == 0) {
    /* The full remaining argument is validated; extra parameters, trailing
     * spaces and long IDs cannot silently turn into a different request. */
    ctl_radar_diag(*p == ' ' ? p + 1 : "");
    return;
  }

  if (strcmp(verb, "join") == 0) {
    printf("[ew-ctl] cmd: join ***\n");
  } else if (strcmp(verb, "mimo-set") == 0) {
    printf("[ew-ctl] cmd: mimo-set ***\n");
  } else if (strcmp(verb, "input") == 0 || strcmp(verb, "submit") == 0) {
    printf("[ew-ctl] cmd: %s (%u bytes)\n", verb, (unsigned)strlen(p));
  } else {
    printf("[ew-ctl] cmd: %s\n", line);
  }

  if (strcmp(verb, "help") == 0) {
    printf("[ew-ctl] @goto warn|wifi|chat  @alert soft|strong|none\n");
    printf("[ew-ctl] @fake 10 20  @scan  @join SSID pass  @forget  @ask text\n");
    printf("[ew-ctl] @ping  @status  @tap x y  @touch down|move|up x y\n");
    printf("[ew-ctl] @snapshot <request_id> (read-only safety snapshot)\n");
    printf("[ew-ctl] @radar-diag <request_id> (read-only radar counters/sample)\n");
    printf("[ew-ctl] @mirror fast|on|normal|hd|off|snap\n");
    printf("[ew-ctl] @mimo-set <key>  @mimo-rollback\n");
    printf("[ew-ctl] @input/@submit <UTF-8 text>  @key backspace|tab|escape\n");
    return;
  }

  if (strcmp(verb, "input") == 0) {
    skip_spaces(&p);
    if (ew_chat_remote_set_text(p) != 0) {
      printf("[ew-ctl] input failed\n");
    } else {
      printf("[ew-ctl] input ok bytes=%u\n", (unsigned)strlen(p));
    }
    return;
  }

  if (strcmp(verb, "submit") == 0) {
    skip_spaces(&p);
    if (ew_chat_remote_set_text(p) != 0 ||
        ew_chat_remote_key("enter") != 0) {
      printf("[ew-ctl] submit failed\n");
    } else {
      printf("[ew-ctl] submit ok bytes=%u\n", (unsigned)strlen(p));
    }
    return;
  }

  if (strcmp(verb, "key") == 0) {
    parse_token(&p, a, sizeof(a));
    if (ew_chat_remote_key(a) != 0) {
      printf("[ew-ctl] key failed: %s\n", a);
    } else {
      printf("[ew-ctl] key ok: %s\n", a);
    }
    return;
  }

  if (strcmp(verb, "mimo-set") == 0) {
    char key[160];
    char result[96];

    parse_token(&p, key, sizeof(key));
    if (key[0] == '\0') {
      printf("[ew-ctl] mimo config failed: missing key\n");
    } else if (ew_llm_configure_mimo(key, result, sizeof(result)) != 0) {
      printf("[ew-ctl] mimo config failed: %s\n", result);
    } else {
      printf("[ew-ctl] %s\n", result);
    }
    memset(key, 0, sizeof(key));
    return;
  }

  if (strcmp(verb, "mimo-rollback") == 0) {
    char result[96];

    if (ew_llm_restore_config(result, sizeof(result)) != 0) {
      printf("[ew-ctl] mimo rollback failed: %s\n", result);
    } else {
      printf("[ew-ctl] %s\n", result);
    }
    return;
  }

  if (strcmp(verb, "mirror") == 0) {
    parse_token(&p, a, sizeof(a));
    if (a[0] == '\0' || strcmp(a, "snap") == 0) {
      ew_mirror_snap_once();
    } else if (strcmp(a, "off") == 0 || strcmp(a, "0") == 0) {
      ew_mirror_set_enabled(0);
    } else if (strcmp(a, "hd") == 0 || strcmp(a, "quality") == 0) {
      ew_mirror_set_mode(EW_MIRROR_HD);
      ew_mirror_set_enabled(1);
    } else if (strcmp(a, "normal") == 0 || strcmp(a, "std") == 0) {
      ew_mirror_set_mode(EW_MIRROR_NORMAL);
      ew_mirror_set_enabled(1);
    } else if (strcmp(a, "fast") == 0 || strcmp(a, "on") == 0 ||
               strcmp(a, "1") == 0) {
      ew_mirror_set_mode(EW_MIRROR_FAST);
      ew_mirror_set_enabled(1);
    } else {
      ew_mirror_set_enabled(!ew_mirror_enabled());
    }
    return;
  }

  if (strcmp(verb, "goto") == 0) {
    parse_token(&p, a, sizeof(a));
    ctl_goto_page(a);
    return;
  }

  if (strcmp(verb, "alert") == 0) {
    const char *reason = "remote";

    parse_token(&p, a, sizeof(a));
    skip_spaces(&p);
    if (*p != '\0') {
      reason = p;
    }
    {
      ew_decision_t decision = {0};
      decision.level = ctl_alert_level(a);
      decision.reason = reason;
      decision.ttc_s = -1.0f;
      if (decision.level < EW_ALERT_NONE) {
        printf("[ew-ctl] invalid alert level\n");
        return;
      }
      (void)ew_agent_emit_decision(&decision, EW_EVENT_SOURCE_SERIAL);
    }
    return;
  }

  if (strcmp(verb, "fake") == 0) {
    float range_m = 10.0f;
    float speed = 20.0f;

    parse_token(&p, a, sizeof(a));
    parse_token(&p, b, sizeof(b));
    if (a[0] != '\0') {
      range_m = (float)atof(a);
    }
    if (b[0] != '\0') {
      speed = (float)atof(b);
    }
    ctl_fake(range_m, speed);
    return;
  }

  if (strcmp(verb, "tap") == 0) {
    int x = 195;
    int y = 225;

    parse_token(&p, a, sizeof(a));
    parse_token(&p, b, sizeof(b));
    if (a[0] != '\0') {
      x = atoi(a);
    }
    if (b[0] != '\0') {
      y = atoi(b);
    }
    ctl_tap((int16_t)x, (int16_t)y);
    return;
  }

  if (strcmp(verb, "touch") == 0) {
    int x;
    int y;

    parse_token(&p, a, sizeof(a));
    parse_token(&p, b, sizeof(b));
    parse_token(&p, c, sizeof(c));
    x = b[0] != '\0' ? atoi(b) : 195;
    y = c[0] != '\0' ? atoi(c) : 225;
    if (strcmp(a, "down") == 0) {
      ctl_touch_down((int16_t)x, (int16_t)y);
    } else if (strcmp(a, "move") == 0) {
      ctl_touch_move((int16_t)x, (int16_t)y);
    } else if (strcmp(a, "up") == 0) {
      ctl_touch_up((int16_t)x, (int16_t)y);
    } else {
      printf("[ew-ctl] touch ? use down|move|up x y\n");
    }
    return;
  }

  if (strcmp(verb, "ping") == 0) {
    ew_wifi_at_ping();
    return;
  }

  if (strcmp(verb, "status") == 0) {
    ew_wifi_at_status();
    return;
  }

  if (strcmp(verb, "scan") == 0 || strcmp(verb, "join") == 0 ||
      strcmp(verb, "forget") == 0 ||
      strcmp(verb, "ask") == 0) {
    ctl_spawn_worker(line);
    return;
  }

  printf("[ew-ctl] unknown verb '%s' (try @help)\n", verb);
}

static void *ctl_reader(void *arg)
{
  int fd = (intptr_t)arg;
  char line[EW_CTL_LINE_MAX];
  int pos = 0;

  (void)arg;
  for (;;) {
    struct pollfd pfd;
    char c;
    ssize_t n;

    pfd.fd = fd;
    pfd.events = POLLIN;
    if (poll(&pfd, 1, 120) <= 0) {
      continue;
    }
    n = read(fd, &c, 1);
    if (n != 1) {
      usleep(50000);
      continue;
    }
    if (c == '\r' || c == '\n') {
      if (pos > 0) {
        line[pos] = '\0';
        if (line[0] == '@') {
          q_push(line + 1);
        }
        pos = 0;
      }
      continue;
    }
    if (pos + 1 < (int)sizeof(line)) {
      line[pos++] = c;
    }
  }
  return NULL;
}

void ew_serial_ctl_start(void)
{
  pthread_t tid;
  int fd;

  if (g_reader_started) {
    return;
  }
  g_reader_started = 1;
  pthread_mutex_init(&g_q.mu, NULL);

  fd = open("/dev/console", O_RDONLY);
  if (fd < 0) {
    fd = STDIN_FILENO;
  }
  if (pthread_create(&tid, NULL, ctl_reader, (void *)(intptr_t)fd) != 0) {
    printf("[ew-ctl] reader thread failed\n");
    return;
  }
  pthread_detach(tid);
  printf("[ew-ctl] remote @ commands on console (PC panel)\n");
}

void ew_serial_ctl_poll(void)
{
  char line[EW_CTL_LINE_MAX];

  while (q_pop(line, sizeof(line))) {
    ctl_dispatch(line);
  }
}

#else

void ew_serial_ctl_start(void)
{
}

void ew_serial_ctl_poll(void)
{
}

#endif
