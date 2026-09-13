/****************************************************************************
 * 读 /dev/console 上以 @ 开头的行；UI 占线时 PC 仍可遥控。
 ****************************************************************************/

#include "ew_serial_ctl.h"
#include "ew_mirror.h"
#include "alert_output.h"
#include "ew_chat.h"
#include "ew_ld2451.h"
#include "ew_llm.h"
#include "ew_wifi_at.h"

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

#define EW_CTL_LINE_MAX 240
#define EW_CTL_Q_MAX    8

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
    printf("[ew-ctl] queue full, drop: %s\n", line);
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

static lv_obj_t *ctl_hit_obj(lv_obj_t *root, lv_point_t *pt)
{
  lv_obj_t *child;
  uint32_t i;
  uint32_t n;

  if (root == NULL) {
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

static void ctl_tap(int16_t x, int16_t y)
{
  lv_point_t pt;
  lv_obj_t *obj;

  pt.x = x;
  pt.y = y;
  obj = ctl_hit_obj(lv_screen_active(), &pt);
  if (obj == NULL) {
    printf("[ew-ctl] tap %d,%d: no widget\n", (int)x, (int)y);
    return;
  }
  lv_obj_send_event(obj, LV_EVENT_PRESSED, NULL);
  lv_obj_send_event(obj, LV_EVENT_CLICKED, NULL);
  lv_obj_send_event(obj, LV_EVENT_RELEASED, NULL);
  printf("[ew-ctl] tap %d,%d -> obj %p\n", (int)x, (int)y, (void *)obj);
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
  return EW_ALERT_SOFT;
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
  alert_output(d.level, d.reason);
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
      printf("[ew-ctl] scan failed\n");
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

static void ctl_dispatch(const char *line)
{
  const char *p = line;
  char verb[32];
  char a[32];
  char b[32];

  parse_token(&p, verb, sizeof(verb));
  if (verb[0] == '\0') {
    return;
  }

  printf("[ew-ctl] cmd: %s\n", line);

  if (strcmp(verb, "help") == 0) {
    printf("[ew-ctl] @goto warn|wifi|chat  @alert soft|strong|none\n");
    printf("[ew-ctl] @fake 10 20  @scan  @join SSID pass  @ask text\n");
    printf("[ew-ctl] @ping  @status  @tap x y\n");
    printf("[ew-ctl] @mirror on|off|snap  (PC 实时镜像)\n");
    return;
  }

  if (strcmp(verb, "mirror") == 0) {
    parse_token(&p, a, sizeof(a));
    if (a[0] == '\0' || strcmp(a, "snap") == 0) {
      ew_mirror_snap_once();
    } else if (strcmp(a, "on") == 0 || strcmp(a, "1") == 0) {
      ew_mirror_set_enabled(1);
    } else if (strcmp(a, "off") == 0 || strcmp(a, "0") == 0) {
      ew_mirror_set_enabled(0);
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
    alert_output(ctl_alert_level(a), reason);
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

  if (strcmp(verb, "ping") == 0) {
    ew_wifi_at_ping();
    return;
  }

  if (strcmp(verb, "status") == 0) {
    ew_wifi_at_status();
    return;
  }

  if (strcmp(verb, "scan") == 0 || strcmp(verb, "join") == 0 ||
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
