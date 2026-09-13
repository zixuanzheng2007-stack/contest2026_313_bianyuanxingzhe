/****************************************************************************
 * 外挂 ESP AT 猫：USART3（PA24 TX / PA25 RX）→ /dev/ttyS2
 * 板上 ttyS 编号：UART1=ttyS0（控制台）、UART2=ttyS1（雷达）、UART3=ttyS2。
 *
 * 上层只看到「扫描 / 连接 / 状态 / HTTP」四件事，AT 细节全部关在本文件里。
 * 所有对外函数自带串口互斥，可从 UI 后台线程直接调用。
 * 模组速率不固定，握手时会自动在常见波特率里找一遍。
 ****************************************************************************/

#include "ew_wifi_at.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __NuttX__

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <termios.h>
#include <unistd.h>
#include <sys/stat.h>
#include <nuttx/config.h>

/* 公网探测目标：阿里公共 DNS，国内外都可达 */
#define EW_WIFI_PING_HOST "223.5.5.5"

static pthread_mutex_t g_at_mu = PTHREAD_MUTEX_INITIALIZER;

/* ESP AT 固件出厂速率不统一，握手不上就整轮试一遍，第一个是最常见的 */
static const speed_t k_baud_code[] = {
  B115200, B921600, B460800, B230400, B57600, B9600
};
static const unsigned k_baud_name[] = {
  115200, 921600, 460800, 230400, 57600, 9600
};
#define EW_AT_BAUD_COUNT (sizeof(k_baud_code) / sizeof(k_baud_code[0]))

/* 上一次握手成功的速率，下次直接用，不必每次重扫 */
static unsigned g_baud_idx;

/****************************************************************************
 * 串口与 AT 原语
 ****************************************************************************/

static void print_rx(const char *s)
{
  char line[200];
  unsigned i;
  unsigned o = 0;

  if (s == NULL) {
    printf("[ew-at] rx=\n");
    return;
  }
  for (i = 0; s[i] != '\0' && o + 1 < sizeof(line); i++) {
    char c = s[i];
    if (c == '\r' || c == '\n') {
      c = ' ';
    } else if ((unsigned char)c < 32u || (unsigned char)c > 126u) {
      c = '.';
    }
    line[o++] = c;
  }
  line[o] = '\0';
  printf("[ew-at] rx=%s\n", line);
  fflush(stdout);
}

static int resp_ok(const char *s)
{
  return strstr(s, "\r\nOK\r\n") != NULL || strncmp(s, "OK\r\n", 4) == 0;
}

static int resp_fail(const char *s)
{
  return strstr(s, "ERROR") != NULL || strstr(s, "FAIL") != NULL;
}

static int resp_got_ip(const char *s)
{
  return strstr(s, "WIFI GOT IP") != NULL || strstr(s, "GOT IP") != NULL;
}

/* AT 字符串字段转义（CWJAP 参数里的 , " \ ） */
static void escape_at_field(const char *in, char *out, unsigned out_sz)
{
  unsigned j = 0;

  if (out_sz == 0) {
    return;
  }
  if (in == NULL) {
    out[0] = '\0';
    return;
  }
  for (; *in != '\0' && j + 2 < out_sz; in++) {
    if (*in == '\\' || *in == ',' || *in == '"') {
      out[j++] = '\\';
    }
    out[j++] = *in;
  }
  out[j] = '\0';
}

/* 串口用 O_NONBLOCK 打开，这里自己轮询计时，不依赖 termios 的 VMIN/VTIME
 * （板上 UART 驱动不保证支持，早期版本就是卡在这个 read 上不返回的）。
 * idle_ms：连续无字节的上限；total_ms：整体上限。want_ip 时等 GOT IP。
 */
static int at_read(int fd, char *out, unsigned out_sz,
                   int idle_ms, int total_ms, int want_ip)
{
  unsigned n = 0;
  int idle = 0;
  int spent = 0;

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (idle < idle_ms && spent < total_ms) {
    char chunk[64];
    ssize_t r = read(fd, chunk, sizeof(chunk));

    if (r > 0) {
      unsigned take = (unsigned)r;
      unsigned off = 0;

      idle = 0;
      while (off < take) {
        if (n + 1 < out_sz) {
          unsigned room = out_sz - n - 1;
          unsigned part = take - off;

          if (part > room) {
            part = room;
          }
          memcpy(out + n, chunk + off, part);
          n += part;
          out[n] = '\0';
          off += part;
        } else {
          /* 缓冲区满：继续读空 UART，避免丢 CWLAP 行 */
          off = take;
        }
      }
      if (resp_fail(out)) {
        return (int)n;
      }
      if (want_ip) {
        if (resp_got_ip(out)) {
          return (int)n;
        }
      } else if (resp_ok(out)) {
        return (int)n;
      }
    } else {
      usleep(20000);
      idle += 20;
      spent += 20;
    }
  }
  return (int)n;
}

/* CWLAP 专用：见到 OK 后继续读到静默，避免异步回包被截断 */
static int at_read_scan(int fd, char *out, unsigned out_sz, int total_ms)
{
  unsigned n = 0;
  int idle = 0;
  int spent = 0;
  int saw_ok = 0;

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (spent < total_ms) {
    char chunk[128];
    ssize_t r = read(fd, chunk, sizeof(chunk));

    if (r > 0) {
      unsigned take = (unsigned)r;
      unsigned off = 0;

      idle = 0;
      while (off < take) {
        if (n + 1 < out_sz) {
          unsigned room = out_sz - n - 1;
          unsigned part = take - off;

          if (part > room) {
            part = room;
          }
          memcpy(out + n, chunk + off, part);
          n += part;
          out[n] = '\0';
          off += part;
        } else {
          off = take;
        }
      }
      if (resp_ok(out)) {
        saw_ok = 1;
      }
    } else {
      usleep(20000);
      spent += 20;
      idle += 20;
      if (saw_ok && idle >= 3000) {
        break;
      }
      if (!saw_ok && idle >= 15000) {
        break;
      }
    }
  }
  return (int)n;
}

static int scan_count_markers(const char *buf)
{
  const char *p = buf;
  int n = 0;

  if (buf == NULL) {
    return 0;
  }
  while ((p = strstr(p, "+CWLAP:")) != NULL) {
    n++;
    p += 7;
  }
  return n;
}

/*
 * UART3 非阻塞驱动会对多字节 write 报告全部成功，但回环实测只发出首字节。
 * 逐字节并留 1 ms 给 TX FIFO，AT 命令和 HTTP 正文共用这条可靠发送路径。
 */
static int write_all(int fd, const char *buf, unsigned len)
{
  unsigned off = 0;
  int stalls = 0;

  while (off < len && stalls < 400) {
    ssize_t w = write(fd, buf + off, 1);

    if (w == 1) {
      off++;
      stalls = 0;
      usleep(1000);
    } else {
      usleep(5000);
      stalls++;
    }
  }
  return (off == len) ? 0 : -1;
}

static int at_tx(int fd, const char *line, char *resp, unsigned resp_sz,
                 int idle_ms, int total_ms, int want_ip)
{
  char tx[192];
  int m;

  m = snprintf(tx, sizeof(tx), "%s\r\n", line);
  if (m > 0) {
    (void)write_all(fd, tx, (unsigned)m);
  }
  /* 凭证不进日志 */
  if (strstr(line, "CWJAP") != NULL) {
    printf("[ew-at] tx=AT+CWJAP=***\n");
  } else {
    printf("[ew-at] tx=%s\n", line);
  }
  fflush(stdout);
  return at_read(fd, resp, resp_sz, idle_ms, total_ms, want_ip);
}

static void set_baud(int fd, speed_t code)
{
  struct termios tio;

  if (tcgetattr(fd, &tio) != 0) {
    return;
  }
  cfmakeraw(&tio);
  cfsetispeed(&tio, code);
  cfsetospeed(&tio, code);
  tio.c_cflag |= (CLOCAL | CREAD);
  tio.c_cc[VMIN] = 0;
  tio.c_cc[VTIME] = 1;
  tcsetattr(fd, TCSANOW, &tio);
  tcflush(fd, TCIOFLUSH);
}

/* 取串口并加锁；失败返回 -1（已解锁）。成对调用 at_end()。 */
static int at_begin(void)
{
  int fd;

  pthread_mutex_lock(&g_at_mu);

  /* 必须 O_NONBLOCK：模组不回话时阻塞 read 会把调用线程永久挂住 */
  fd = open(EW_WIFI_AT_DEV, O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (fd < 0) {
    printf("[ew-at] open %s failed errno=%d\n", EW_WIFI_AT_DEV, errno);
    pthread_mutex_unlock(&g_at_mu);
    return -1;
  }

  set_baud(fd, k_baud_code[g_baud_idx]);
  return fd;
}

static void at_end(int fd)
{
  if (fd >= 0) {
    close(fd);
  }
  pthread_mutex_unlock(&g_at_mu);
}

/* 发一条 AT 看有没有 OK。上电后第一条常被吃掉，所以调用方给两次机会。 */
static int probe_at(int fd)
{
  char resp[128];

  (void)at_tx(fd, "AT", resp, sizeof(resp), 400, 900, 0);
  return resp_ok(resp) ? 0 : -1;
}

/* 在各个速率上找模组；命中时更新 g_baud_idx。0 = 找到。 */
static int sync_baud(int fd)
{
  unsigned i;

  if (probe_at(fd) == 0 || probe_at(fd) == 0) {
    return 0;
  }
  for (i = 0; i < EW_AT_BAUD_COUNT; i++) {
    if (i == g_baud_idx) {
      continue;
    }
    set_baud(fd, k_baud_code[i]);
    if (probe_at(fd) == 0 || probe_at(fd) == 0) {
      printf("[ew-at] modem speaks %u baud\n", k_baud_name[i]);
      g_baud_idx = i;
      return 0;
    }
  }
  return -1;
}

/* 轻量握手：扫描/查询用，失败时不 RST（避免扫到一半被复位）。 */
static int at_wake_light(int fd)
{
  char resp[160];

  if (sync_baud(fd) != 0) {
    return -1;
  }
  (void)at_tx(fd, "ATE0", resp, sizeof(resp), 500, 800, 0);
  (void)at_tx(fd, "AT+CWMODE=1", resp, sizeof(resp), 800, 1500, 0);
  return 0;
}

/* 握手 + 关回显 + 站点模式。0 = 模组可用。 */
static int at_wake(int fd)
{
  char resp[160];

  if (sync_baud(fd) != 0) {
    /* 所有速率都没声音，复位模组再给最后一次机会 */
    g_baud_idx = 0;
    set_baud(fd, k_baud_code[0]);
    (void)at_tx(fd, "AT+RST", resp, sizeof(resp), 1500, 2500, 0);
    usleep(1500000);
    if (sync_baud(fd) != 0) {
      printf("[ew-at] silent at every baud; check PA24->ESP RX, "
             "PA25->ESP TX, common GND, and that ESP runs AT firmware\n");
      fflush(stdout);
      return -1;
    }
  }

  printf("[ew-at] wake ok @%u baud\n", k_baud_name[g_baud_idx]);
  fflush(stdout);
  (void)at_tx(fd, "ATE0", resp, sizeof(resp), 500, 800, 0);
  (void)at_tx(fd, "AT+CWMODE=1", resp, sizeof(resp), 800, 1500, 0);
  return 0;
}

/****************************************************************************
 * 响应解析
 ****************************************************************************/

/* 抄出 p 指向的带引号字段（p 必须指向起始引号），返回引号后的位置。 */
static const char *copy_quoted(const char *p, char *out, unsigned out_sz)
{
  unsigned i = 0;

  if (p == NULL || *p != '"') {
    if (out_sz > 0) {
      out[0] = '\0';
    }
    return NULL;
  }
  p++;
  while (*p != '\0' && *p != '"') {
    if (*p == '\\' && p[1] != '\0') {
      p++;
    }
    if (i + 1 < out_sz) {
      out[i++] = *p;
    }
    p++;
  }
  if (out_sz > 0) {
    out[i] = '\0';
  }
  return (*p == '"') ? p + 1 : NULL;
}

/* +CIFSR:STAIP,"192.168.1.23" → ip。0 = 拿到非零地址。 */
static int parse_staip(const char *resp, char *ip, unsigned ip_sz)
{
  const char *p = strstr(resp, "STAIP,");

  if (ip_sz > 0) {
    ip[0] = '\0';
  }
  if (p == NULL) {
    return -1;
  }
  if (copy_quoted(p + 6, ip, ip_sz) == NULL) {
    return -1;
  }
  if (ip[0] == '\0' || strcmp(ip, "0.0.0.0") == 0) {
    return -1;
  }
  return 0;
}

/* AT+CWJAP 失败码 → 屏上短语 */
static const char *jap_fail_text(const char *resp)
{
  const char *p = strstr(resp, "+CWJAP:");

  if (p != NULL) {
    switch (p[7]) {
      case '1':
        return "JOIN TIMEOUT";
      case '2':
        return "BAD PASSWORD";
      case '3':
        return "AP NOT FOUND";
      default:
        break;
    }
  }
  return "JOIN FAIL";
}

/****************************************************************************
 * 凭证存取（/data/ew_wifi.conf，两行 key=value）
 ****************************************************************************/

static int cred_save(const char *ssid, const char *pass)
{
  FILE *fp = fopen(EW_WIFI_CONF, "w");

  if (fp == NULL) {
    printf("[ew-at] save cred failed errno=%d\n", errno);
    return -1;
  }
  fprintf(fp, "ssid=%s\npass=%s\n", ssid, pass ? pass : "");
  fclose(fp);
  (void)chmod(EW_WIFI_CONF, 0600);
  printf("[ew-at] cred saved for %s\n", ssid);
  return 0;
}

int ew_wifi_cred_load(char *ssid, unsigned ssid_sz, char *pass, unsigned pass_sz)
{
  char line[EW_WIFI_SSID_MAX + EW_WIFI_PASS_MAX + 8];
  FILE *fp;
  int got_ssid = 0;

  if (ssid == NULL || ssid_sz == 0) {
    return -1;
  }
  ssid[0] = '\0';
  if (pass != NULL && pass_sz > 0) {
    pass[0] = '\0';
  }

  fp = fopen(EW_WIFI_CONF, "r");
  if (fp == NULL) {
    return -1;
  }
  while (fgets(line, sizeof(line), fp) != NULL) {
    char *eq = strchr(line, '=');
    size_t len;

    if (eq == NULL) {
      continue;
    }
    *eq++ = '\0';
    len = strlen(eq);
    while (len > 0 && (eq[len - 1] == '\n' || eq[len - 1] == '\r')) {
      eq[--len] = '\0';
    }
    if (strcmp(line, "ssid") == 0) {
      snprintf(ssid, ssid_sz, "%s", eq);
      got_ssid = (ssid[0] != '\0');
    } else if (strcmp(line, "pass") == 0 && pass != NULL && pass_sz > 0) {
      snprintf(pass, pass_sz, "%s", eq);
    }
  }
  fclose(fp);
  return got_ssid ? 0 : -1;
}

/****************************************************************************
 * 对外接口
 ****************************************************************************/

int ew_wifi_at_cmd(const char *at_line)
{
  char line[160];
  char resp[512];
  int fd;
  int n;
  size_t len;

  if (at_line == NULL || at_line[0] == '\0') {
    at_line = "AT";
  }
  snprintf(line, sizeof(line), "%s", at_line);
  len = strlen(line);
  while (len > 0 && (line[len - 1] == '\r' || line[len - 1] == '\n')) {
    line[--len] = '\0';
  }

  fd = at_begin();
  if (fd < 0) {
    return 1;
  }
  n = at_tx(fd, line, resp, sizeof(resp), 2500, 8000, 0);
  at_end(fd);

  print_rx(resp);
  if (n > 0 && (resp_ok(resp) || resp_got_ip(resp))) {
    return 0;
  }
  if (n <= 0) {
    printf("[ew-at] no reply\n");
  }
  return (n > 0) ? 2 : 3;
}

int ew_wifi_at_ping(void)
{
  return ew_wifi_at_cmd("AT");
}

int ew_wifi_at_status(void)
{
  int rc = 0;

  printf("[ew-at] --- status ---\n");
  if (ew_wifi_at_cmd("AT+CWJAP?") != 0) {
    rc = 2;
  }
  if (ew_wifi_at_cmd("AT+CIFSR") != 0) {
    rc = 2;
  }
  return rc;
}

/* 已持有串口时的公网探测：0 = 通 */
static int inet_ping(int fd)
{
  char resp[192];
  int n;

  n = at_tx(fd, "AT+PING=\"" EW_WIFI_PING_HOST "\"", resp, sizeof(resp),
            5000, 8000, 0);
  return (n > 0 && strstr(resp, "+PING:") != NULL && !resp_fail(resp)) ? 0 : -1;
}

ew_wifi_state_t ew_wifi_probe(int check_inet, char *ip, unsigned ip_sz)
{
  char resp[256];
  char addr[24];
  ew_wifi_state_t st;
  int fd;

  if (ip != NULL && ip_sz > 0) {
    ip[0] = '\0';
  }

  fd = at_begin();
  if (fd < 0) {
    return EW_WIFI_DOWN;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    return EW_WIFI_DOWN;
  }

  (void)at_tx(fd, "AT+CIFSR", resp, sizeof(resp), 1500, 4000, 0);
  if (parse_staip(resp, addr, sizeof(addr)) != 0) {
    at_end(fd);
    return EW_WIFI_IDLE;
  }

  st = EW_WIFI_JOINED;
  if (check_inet && inet_ping(fd) == 0) {
    st = EW_WIFI_ONLINE;
  }
  at_end(fd);

  if (ip != NULL && ip_sz > 0) {
    snprintf(ip, ip_sz, "%s", addr);
  }
  return st;
}

static int scan_insert_ap(ew_wifi_ap_t *aps, int max, int *count,
                          const ew_wifi_ap_t *ap)
{
  int i;

  if (ap == NULL || ap->ssid[0] == '\0') {
    return 0;
  }
  for (i = 0; i < *count; i++) {
    if (strcmp(aps[i].ssid, ap->ssid) == 0) {
      if (ap->rssi > aps[i].rssi) {
        aps[i] = *ap;
      }
      return 0;
    }
  }
  if (*count >= max) {
    return 0;
  }
  aps[*count] = *ap;
  (*count)++;
  return 0;
}

static int scan_parse_line(const char *line, ew_wifi_ap_t *ap)
{
  const char *p;
  const char *q;

  if (line == NULL || ap == NULL) {
    return -1;
  }
  p = strstr(line, "+CWLAP:");
  if (p == NULL) {
    return -1;
  }
  p += 7;
  if (*p == '(') {
    p++;
  }
  q = p;
  memset(ap, 0, sizeof(*ap));
  ap->open = (*q == '0');
  q = strchr(q, ',');
  if (q == NULL) {
    return -1;
  }
  q = copy_quoted(q + 1, ap->ssid, sizeof(ap->ssid));
  if (q == NULL || *q != ',') {
    return -1;
  }
  ap->rssi = atoi(q + 1);
  if (ap->ssid[0] == '\0') {
    snprintf(ap->ssid, sizeof(ap->ssid), "[hidden]");
  }
  return 0;
}

static int scan_from_buf(const char *buf, ew_wifi_ap_t *aps, int max, int *count)
{
  const char *p;
  char line[256];

  if (buf == NULL || aps == NULL || count == NULL) {
    return -1;
  }
  for (p = buf; (p = strstr(p, "+CWLAP:")) != NULL; ) {
    ew_wifi_ap_t ap;
    const char *eol = strchr(p, '\n');
    unsigned len;

    if (eol != NULL) {
      len = (unsigned)(eol - p);
      if (len >= sizeof(line)) {
        len = sizeof(line) - 1;
      }
      memcpy(line, p, len);
      line[len] = '\0';
      if (scan_parse_line(line, &ap) == 0) {
        scan_insert_ap(aps, max, count, &ap);
      }
      p = eol + 1;
    } else {
      if (scan_parse_line(p, &ap) == 0) {
        scan_insert_ap(aps, max, count, &ap);
      }
      break;
    }
  }
  return *count;
}

static void scan_sort_rssi(ew_wifi_ap_t *aps, int count)
{
  int i;

  for (i = 1; i < count; i++) {
    ew_wifi_ap_t key = aps[i];
    int j = i - 1;

    while (j >= 0 && aps[j].rssi < key.rssi) {
      aps[j + 1] = aps[j];
      j--;
    }
    aps[j + 1] = key;
  }
}

static int scan_tx_cwlap(int fd, char *buf, unsigned bufsz)
{
  char tx[16];
  int m;

  tcflush(fd, TCIFLUSH);
  memset(buf, 0, bufsz);
  m = snprintf(tx, sizeof(tx), "AT+CWLAP");
  if (m <= 0) {
    return -1;
  }
  if (write_all(fd, tx, (unsigned)m) != 0) {
    return -1;
  }
  if (write_all(fd, "\r\n", 2) != 0) {
    return -1;
  }
  printf("[ew-at] tx=AT+CWLAP (scan read)\n");
  fflush(stdout);
  return at_read_scan(fd, buf, bufsz, 45000);
}

/* 单次 CWLAP；use_opt=0 走模组默认全字段（兼容性最好） */
static int scan_run_once(int fd, ew_wifi_ap_t *aps, int max, int *count,
                         int use_opt)
{
  static char buf[16384];
  char opt_resp[128];
  int n;
  int before = *count;
  int markers;

  if (use_opt) {
    (void)at_tx(fd, "AT+CWLAPOPT=1,7", opt_resp, sizeof(opt_resp), 800, 1500, 0);
  }
  n = scan_tx_cwlap(fd, buf, sizeof(buf));
  if (n <= 0) {
    printf("[ew-at] CWLAP no reply (n=%d)\n", n);
    return -1;
  }
  markers = scan_count_markers(buf);
  scan_from_buf(buf, aps, max, count);
  printf("[ew-at] CWLAP opt=%d bytes=%d markers=%d parsed=%d (+%d)\n",
         use_opt, n, markers, *count, *count - before);
  fflush(stdout);
  return *count;
}

/* 定向扫某个 SSID（隐藏热点 / 漏扫时用 AT+CWLAP="name"） */
static int scan_target_ssid(int fd, const char *ssid, ew_wifi_ap_t *aps,
                            int max, int *count)
{
  char essid[EW_WIFI_SSID_MAX * 2];
  char cmd[EW_WIFI_SSID_MAX * 2 + 16];
  static char buf[2048];
  int n;

  if (ssid == NULL || ssid[0] == '\0') {
    return 0;
  }
  escape_at_field(ssid, essid, sizeof(essid));
  snprintf(cmd, sizeof(cmd), "AT+CWLAP=\"%s\"", essid);
  if (write_all(fd, cmd, strlen(cmd)) != 0) {
    return -1;
  }
  if (write_all(fd, "\r\n", 2) != 0) {
    return -1;
  }
  memset(buf, 0, sizeof(buf));
  n = at_read_scan(fd, buf, sizeof(buf), 20000);
  if (n <= 0) {
    return -1;
  }
  scan_from_buf(buf, aps, max, count);
  printf("[ew-at] CWLAP target \"%s\" markers=%d parsed=%d\n",
         ssid, scan_count_markers(buf), *count);
  fflush(stdout);
  return *count;
}

int ew_wifi_scan(ew_wifi_ap_t *aps, int max)
{
  char resp[160];
  char saved_ssid[EW_WIFI_SSID_MAX];
  int count = 0;
  int fd;

  if (aps == NULL || max <= 0) {
    return -1;
  }

  fd = at_begin();
  if (fd < 0) {
    return -1;
  }
  if (at_wake_light(fd) != 0) {
    /* 轻量握手失败再试完整 wake（含 RST） */
    if (at_wake(fd) != 0) {
      at_end(fd);
      return -1;
    }
  }

  /* 扫描前：断连 + 禁休眠 + 中国区信道（连上 AP 时被动扫描常只剩 1～2 条） */
  (void)at_tx(fd, "AT+CWQAP", resp, sizeof(resp), 1500, 4000, 0);
  (void)at_tx(fd, "AT+SLEEP=0", resp, sizeof(resp), 800, 1500, 0);
  (void)at_tx(fd, "AT+COUNTRY=\"CN\",1", resp, sizeof(resp), 800, 1500, 0);
  usleep(500000);

  (void)scan_run_once(fd, aps, max, &count, 0);

  /* 仍很少：等 1s 再扫第二轮 */
  if (count <= 3) {
    usleep(1000000);
    (void)scan_run_once(fd, aps, max, &count, 0);
  }

  /* 已保存 SSID 定向补扫（如 Pura80pro+ 漏扫） */
  if (ew_wifi_cred_load(saved_ssid, sizeof(saved_ssid), NULL, 0) == 0) {
    int before = count;

    (void)scan_target_ssid(fd, saved_ssid, aps, max, &count);
    if (count == before) {
      (void)scan_target_ssid(fd, saved_ssid, aps, max, &count);
    }
  }

  scan_sort_rssi(aps, count);
  at_end(fd);

  printf("[ew-at] scan found %d ap\n", count);
  fflush(stdout);
  return count;
}

int ew_wifi_join(const char *ssid, const char *pass, char *out, unsigned out_sz)
{
  char essid[EW_WIFI_SSID_MAX * 2];
  char epass[EW_WIFI_PASS_MAX * 2];
  char cmd[EW_WIFI_SSID_MAX + EW_WIFI_PASS_MAX + 32];
  char resp[384];
  char addr[24];
  int fd;
  int n;
  int online;

  if (out != NULL && out_sz > 0) {
    out[0] = '\0';
  }
  if (ssid == NULL || ssid[0] == '\0') {
    return -1;
  }

  fd = at_begin();
  if (fd < 0) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "NO MODEM");
    }
    return 1;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "NO MODEM");
    }
    return 2;
  }

  /* 清掉旧关联，避免 CWJAP 直接失败 */
  (void)at_tx(fd, "AT+CWQAP", resp, sizeof(resp), 1500, 4000, 0);

  escape_at_field(ssid, essid, sizeof(essid));
  escape_at_field(pass ? pass : "", epass, sizeof(epass));
  snprintf(cmd, sizeof(cmd), "AT+CWJAP=\"%s\",\"%s\"", essid, epass);
  n = at_tx(fd, cmd, resp, sizeof(resp), 25000, 35000, 1);
  if (n <= 0 || resp_fail(resp) || !(resp_got_ip(resp) || resp_ok(resp))) {
    const char *why = jap_fail_text(resp);

    at_end(fd);
    print_rx(resp);
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "%s", why);
    }
    printf("[ew-at] join %s: %s\n", ssid, why);
    return 3;
  }

  (void)at_tx(fd, "AT+CIFSR", resp, sizeof(resp), 1500, 4000, 0);
  if (parse_staip(resp, addr, sizeof(addr)) != 0) {
    snprintf(addr, sizeof(addr), "?");
  }
  online = (inet_ping(fd) == 0);
  at_end(fd);

  (void)cred_save(ssid, pass);
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, online ? "WIFI ON %s" : "WIFI LAN %s", addr);
  }
  printf("[ew-at] join %s ok ip=%s inet=%d\n", ssid, addr, online);
  fflush(stdout);
  return 0;
}

int ew_wifi_forget(void)
{
  int fd = at_begin();

  if (fd >= 0) {
    char resp[128];

    (void)at_tx(fd, "AT+CWQAP", resp, sizeof(resp), 1500, 3000, 0);
    at_end(fd);
  }
  (void)unlink(EW_WIFI_CONF);
  printf("[ew-at] credentials cleared\n");
  return 0;
}

int ew_wifi_bringup(char *out, unsigned out_sz)
{
  char ssid[EW_WIFI_SSID_MAX];
  char pass[EW_WIFI_PASS_MAX];
  char ip[24];
  ew_wifi_state_t st;

  if (out != NULL && out_sz > 0) {
    out[0] = '\0';
  }

  /* 模组自身会记住上次的 AP，先看它是不是已经上线了 */
  st = ew_wifi_probe(1, ip, sizeof(ip));
  if (st == EW_WIFI_DOWN) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "NO MODEM");
    }
    return 2;
  }
  if (st != EW_WIFI_IDLE) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, st == EW_WIFI_ONLINE ? "WIFI ON %s" : "WIFI LAN %s",
               ip);
    }
    printf("[ew-at] already joined ip=%s inet=%d\n", ip, st == EW_WIFI_ONLINE);
    return 0;
  }

  if (ew_wifi_cred_load(ssid, sizeof(ssid), pass, sizeof(pass)) != 0) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "NO WIFI");
    }
    printf("[ew-at] AT ok, no saved credentials (use WiFi page)\n");
    return 0;
  }

  return ew_wifi_join(ssid, pass, out, out_sz);
}

/****************************************************************************
 * HTTPS POST（给 LLM 用）
 ****************************************************************************/

static int wait_prompt(int fd, int timeout_ms)
{
  char buf[96];
  unsigned n = 0;
  int waited = 0;

  buf[0] = '\0';
  while (waited < timeout_ms && n + 1 < sizeof(buf)) {
    char c;
    int r = read(fd, &c, 1);

    if (r == 1) {
      buf[n++] = c;
      buf[n] = '\0';
      if (strchr(buf, '>') != NULL) {
        return 0;
      }
      if (resp_fail(buf)) {
        return -1;
      }
      waited = 0;
    } else {
      usleep(20000);
      waited += 20;
    }
  }
  return -1;
}

/* 读到对端 CLOSED 或静默超时为止 */
static int collect_body(int fd, char *out, unsigned out_sz, int idle_ms)
{
  unsigned n = 0;
  int idle = 0;

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (idle < idle_ms && n + 1 < out_sz) {
    char c;
    int r = read(fd, &c, 1);

    if (r == 1) {
      out[n++] = c;
      out[n] = '\0';
      idle = 0;
      if (n > 24 && strstr(out, "CLOSED") != NULL) {
        return (int)n;
      }
    } else {
      usleep(20000);
      idle += 20;
    }
  }
  return (int)n;
}

int ew_wifi_http_ssl_post(const char *host, unsigned port, const char *path,
                          const char *bearer, const char *json_body,
                          char *resp, unsigned resp_sz)
{
  static char http[1800];
  char cmd[192];
  char scratch[512];
  char *dst;
  unsigned dst_sz;
  int fd;
  int n;
  unsigned hlen;

  if (host == NULL || path == NULL || json_body == NULL) {
    return -1;
  }
  if (port == 0) {
    port = 443;
  }

  hlen = (unsigned)snprintf(http, sizeof(http),
                            "POST %s HTTP/1.1\r\n"
                            "Host: %s\r\n"
                            "Authorization: Bearer %s\r\n"
                            "Content-Type: application/json\r\n"
                            "Connection: close\r\n"
                            "Content-Length: %u\r\n"
                            "\r\n"
                            "%s",
                            path, host, bearer ? bearer : "",
                            (unsigned)strlen(json_body), json_body);
  if (hlen >= sizeof(http) - 1) {
    printf("[ew-at] http too long\n");
    return -1;
  }

  dst = (resp != NULL && resp_sz > 8) ? resp : scratch;
  dst_sz = (resp != NULL && resp_sz > 8) ? resp_sz : sizeof(scratch);
  dst[0] = '\0';

  fd = at_begin();
  if (fd < 0) {
    return -1;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    printf("[ew-at] http: modem down\n");
    return -1;
  }

  (void)at_tx(fd, "AT+CIPMUX=0", scratch, sizeof(scratch), 800, 1500, 0);
  (void)at_tx(fd, "AT+CIPMODE=0", scratch, sizeof(scratch), 800, 1500, 0);
  (void)at_tx(fd, "AT+CIPCLOSE", scratch, sizeof(scratch), 800, 1500, 0);
  (void)at_tx(fd, "AT+CIPSSLCCONF=0", scratch, sizeof(scratch), 800, 1500, 0);

  snprintf(cmd, sizeof(cmd), "AT+CIPSTART=\"SSL\",\"%s\",%u", host, port);
  n = at_tx(fd, cmd, scratch, sizeof(scratch), 8000, 12000, 0);
  if (n <= 0 || resp_fail(scratch) ||
      (strstr(scratch, "CONNECT") == NULL && !resp_ok(scratch))) {
    print_rx(scratch);
    at_end(fd);
    printf("[ew-at] SSL CIPSTART fail\n");
    return -1;
  }

  snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%u", hlen);
  (void)at_tx(fd, cmd, scratch, sizeof(scratch), 1500, 2000, 0);
  if (strchr(scratch, '>') == NULL && wait_prompt(fd, 3000) != 0) {
    at_end(fd);
    printf("[ew-at] CIPSEND no prompt\n");
    return -1;
  }

  if (write_all(fd, http, hlen) != 0) {
    at_end(fd);
    printf("[ew-at] http body write stalled\n");
    return -1;
  }
  n = collect_body(fd, dst, dst_sz, 25000);
  (void)at_tx(fd, "AT+CIPCLOSE", scratch, sizeof(scratch), 800, 1500, 0);
  at_end(fd);

  printf("[ew-at] http bytes=%d\n", n);
  return (n > 16) ? 0 : -1;
}

#else /* !__NuttX__ —— host smoke 用的空实现 */

int ew_wifi_at_cmd(const char *at_line)
{
  printf("[ew-at] host stub cmd=%s\n", at_line ? at_line : "AT");
  return 0;
}

int ew_wifi_at_ping(void)
{
  return ew_wifi_at_cmd("AT");
}

int ew_wifi_at_status(void)
{
  printf("[ew-at] host stub status\n");
  return 0;
}

ew_wifi_state_t ew_wifi_probe(int check_inet, char *ip, unsigned ip_sz)
{
  (void)check_inet;
  if (ip != NULL && ip_sz > 0) {
    ip[0] = '\0';
  }
  return EW_WIFI_DOWN;
}

int ew_wifi_scan(ew_wifi_ap_t *aps, int max)
{
  (void)aps;
  (void)max;
  return 0;
}

int ew_wifi_join(const char *ssid, const char *pass, char *out, unsigned out_sz)
{
  (void)ssid;
  (void)pass;
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, "host stub");
  }
  return -1;
}

int ew_wifi_forget(void)
{
  return 0;
}

int ew_wifi_cred_load(char *ssid, unsigned ssid_sz, char *pass, unsigned pass_sz)
{
  (void)pass;
  (void)pass_sz;
  if (ssid != NULL && ssid_sz > 0) {
    ssid[0] = '\0';
  }
  return -1;
}

int ew_wifi_bringup(char *out, unsigned out_sz)
{
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, "AT STUB");
  }
  return 0;
}

int ew_wifi_http_ssl_post(const char *host, unsigned port, const char *path,
                          const char *bearer, const char *json_body,
                          char *resp, unsigned resp_sz)
{
  (void)host;
  (void)port;
  (void)path;
  (void)bearer;
  (void)json_body;
  if (resp != NULL && resp_sz > 0) {
    snprintf(resp, resp_sz, "host stub");
  }
  return -1;
}

#endif /* __NuttX__ */
