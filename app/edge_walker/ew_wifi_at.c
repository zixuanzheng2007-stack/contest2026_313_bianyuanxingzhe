/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 外挂 ESP AT 猫：USART3（PA24 TX / PA25 RX）→ /dev/ttyS2
 * 板上 ttyS 编号：UART1=ttyS0（控制台）、UART2=ttyS1（雷达）、UART3=ttyS2。
 *
 * 上层只看到「扫描 / 连接 / 状态 / HTTP」四件事，AT 细节全部关在本文件里。
 * 所有对外函数自带串口互斥，可从 UI 后台线程直接调用。
 * 模组速率不固定，握手时会自动在常见波特率里找一遍。
 ****************************************************************************/

#include "ew_wifi_at.h"
#include "ew_net_state.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __NuttX__

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <nuttx/config.h>

/* 手机热点可能屏蔽全部 ICMP；PING 失败后用公网 DNS 解析判定。 */
#define EW_WIFI_PING_HOST "223.5.5.5"
#define EW_WIFI_DNS_HOST  "www.baidu.com"

static pthread_mutex_t g_at_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t g_scan_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t g_scan_state_mu = PTHREAD_MUTEX_INITIALIZER;

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

/* UI/NSH 登记的定向补扫 SSID（不必已写入 ew_wifi.conf） */
static char g_scan_hints[EW_WIFI_HINT_MAX][EW_WIFI_SSID_MAX];
static int g_scan_hint_n;
static ew_wifi_ap_t g_scan_cache[EW_WIFI_SCAN_MAX];
static int g_scan_cache_count;
static uint32_t g_scan_cache_ms;

#define EW_WIFI_SCAN_CACHE_MS 5000u

static uint32_t monotonic_ms(void)
{
  struct timespec ts;

  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint32_t)((uint64_t)ts.tv_sec * 1000u +
                    (uint64_t)ts.tv_nsec / 1000000u);
}

static int scan_cache_copy(ew_wifi_ap_t *aps, int max, int allow_stale)
{
  uint32_t now = monotonic_ms();
  int n = 0;

  pthread_mutex_lock(&g_scan_state_mu);
  if (g_scan_cache_ms != 0 &&
      (allow_stale || (now - g_scan_cache_ms) <= EW_WIFI_SCAN_CACHE_MS)) {
    n = g_scan_cache_count;
    if (n > max) {
      n = max;
    }
    if (n > 0) {
      memcpy(aps, g_scan_cache, (size_t)n * sizeof(aps[0]));
    }
  } else {
    n = -1;
  }
  pthread_mutex_unlock(&g_scan_state_mu);
  return n;
}

static void scan_cache_store(const ew_wifi_ap_t *aps, int count)
{
  pthread_mutex_lock(&g_scan_state_mu);
  g_scan_cache_count = count;
  if (count > 0) {
    memcpy(g_scan_cache, aps, (size_t)count * sizeof(aps[0]));
  }
  g_scan_cache_ms = monotonic_ms();
  pthread_mutex_unlock(&g_scan_state_mu);
}

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
  printf("[ESP-AT RX] %s\n", line);
  fflush(stdout);
}

static void print_rx_blob(const char *buf, int n)
{
  int i;

  if (buf == NULL || n <= 0) {
    return;
  }
  for (i = 0; i < n; ) {
    int chunk = n - i;

    if (chunk > 480) {
      chunk = 480;
    }
    printf("[ESP-AT RX] %.*s", chunk, buf + i);
    if (buf[i + chunk - 1] != '\n') {
      printf("\n");
    }
    fflush(stdout);
    i += chunk;
  }
}

/* AT responses are small. Independently bound work if the clock stalls or a
 * broken UART keeps replaying bytes; neither buffer saturation nor activity
 * may turn a finite command into an unbounded read loop. */
#define EW_AT_RX_READ_LIMIT 8192u
#define EW_AT_RX_BYTE_LIMIT (512u * 1024u)

static int at_rx_limit_reached(uint32_t started, int total_ms,
                                unsigned reads, unsigned bytes)
{
  return total_ms <= 0 ||
         (uint32_t)(monotonic_ms() - started) >= (uint32_t)total_ms ||
         reads >= EW_AT_RX_READ_LIMIT || bytes >= EW_AT_RX_BYTE_LIMIT;
}

static void at_drain_rx(int fd, int max_ms)
{
  int spent = 0;
  unsigned reads = 0;
  unsigned bytes = 0;
  uint32_t started = monotonic_ms();

  while (spent < max_ms &&
         !at_rx_limit_reached(started, max_ms, reads, bytes)) {
    char scratch[128];
    ssize_t r = read(fd, scratch, sizeof(scratch));

    reads++;
    if (r > 0) {
      bytes += (unsigned)r;
    } else {
      usleep(20000);
      spent += 20;
    }
  }
  if (bytes > 0) {
    /* Drained content may include credentials or stale HTTP payloads. Only
     * report the count once, rather than echoing an unbounded input stream. */
    printf("[ew-at] drain discarded=%u bytes\n", bytes);
  }
}

static int resp_ok(const char *s)
{
  if (s == NULL) {
    return 0;
  }
  if (strstr(s, "\r\nOK\r\n") != NULL) {
    return 1;
  }
  if (strncmp(s, "OK\r\n", 4) == 0) {
    return 1;
  }
  /* A suffix such as NOTOK is not an OK response line. */
  return 0;
}

static int resp_fail(const char *s)
{
  return strstr(s, "ERROR") != NULL || strstr(s, "FAIL") != NULL;
}

static int resp_got_ip(const char *s)
{
  return strstr(s, "WIFI GOT IP") != NULL || strstr(s, "GOT IP") != NULL;
}

static int resp_wifi_connected(const char *s)
{
  return s != NULL && strstr(s, "WIFI CONNECTED") != NULL;
}

static int inet_probe(int fd);
static int scan_count_markers(const char *buf);

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
  unsigned reads = 0;
  unsigned bytes = 0;
  uint32_t started = monotonic_ms();

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (idle < idle_ms && spent < total_ms &&
         !at_rx_limit_reached(started, total_ms, reads, bytes)) {
    char chunk[64];
    ssize_t r = read(fd, chunk, sizeof(chunk));

    reads++;
    if (r > 0) {
      unsigned take = (unsigned)r;
      unsigned off = 0;

      bytes += take;
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
  unsigned reads = 0;
  unsigned bytes = 0;
  uint32_t started = monotonic_ms();

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (spent < total_ms &&
         !at_rx_limit_reached(started, total_ms, reads, bytes)) {
    char chunk[128];
    ssize_t r = read(fd, chunk, sizeof(chunk));

    reads++;
    if (r > 0) {
      unsigned take = (unsigned)r;
      unsigned off = 0;

      bytes += take;
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

  /* Console TX masks IRQs on this BSP. Log before the modem can reply. */
  /* 凭证不进日志 */
  if (strstr(line, "CWJAP") != NULL) {
    printf("[ew-at] tx=AT+CWJAP=***\n");
  } else {
    printf("[ew-at] tx=%s\n", line);
  }
  fflush(stdout);
  m = snprintf(tx, sizeof(tx), "%s\r\n", line);
  if (m <= 0 || (unsigned)m >= sizeof(tx) ||
      write_all(fd, tx, (unsigned)m) != 0) {
    if (resp_sz > 0) {
      resp[0] = '\0';
    }
    return -1;
  }
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
static int at_lock(void)
{
  unsigned waited;
  int rc;

  /* A scan or HTTPS request may own the modem for tens of seconds. A new
   * caller must fail as BUSY instead of stalling the UI/command queue. */
  for (waited = 0; waited <= 500; waited += 10) {
    rc = pthread_mutex_trylock(&g_at_mu);
    if (rc == 0) {
      return 0;
    }
    if (rc != EBUSY) {
      errno = rc;
      return -1;
    }
    if (waited < 500) {
      usleep(10000);
    }
  }
  errno = EBUSY;
  return -1;
}

static int at_begin(void)
{
  int fd;

  if (at_lock() != 0) {
    return -1;
  }

  /* 必须 O_NONBLOCK：模组不回话时阻塞 read 会把调用线程永久挂住 */
  fd = open(EW_WIFI_AT_DEV, O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (fd < 0) {
    int saved_errno = errno;
    printf("[ew-at] open %s failed errno=%d\n", EW_WIFI_AT_DEV, saved_errno);
    pthread_mutex_unlock(&g_at_mu);
    errno = saved_errno;
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
  unsigned i;
  unsigned printable = 0;
  unsigned zero = 0;
  int n;

  n = at_tx(fd, "AT", resp, sizeof(resp), 400, 900, 0);
  for (i = 0; n > 0 && i < (unsigned)n; i++) {
    unsigned char byte = (unsigned char)resp[i];
    if (byte >= 32u && byte <= 126u) printable++;
    if (byte == 0) zero++;
  }
  /* Counts and protocol markers only: never log a stale HTTP payload or key.
   * Emit after receiving so console TX cannot mask the UART reply IRQ. */
  printf("[ew-at] probe rx=%d ok=%d printable=%u zero=%u at_echo=%d ok_text=%d\n",
         n, resp_ok(resp) ? 1 : 0, printable, zero,
         n > 0 && strstr(resp, "AT") != NULL ? 1 : 0,
         n > 0 && strstr(resp, "OK") != NULL ? 1 : 0);
  return resp_ok(resp) ? 0 : -1;
}

/* 在各个速率上找模组；命中时更新 g_baud_idx。0 = 找到。 */
static int sync_baud(int fd)
{
  unsigned i;

#if EW_AT_BAUD_FIXED
  g_baud_idx = 0;
  set_baud(fd, k_baud_code[0]);
  if (probe_at(fd) == 0 || probe_at(fd) == 0) {
    return 0;
  }
  return -1;
#else
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
#endif
}

static int at_station_setup(int fd)
{
  char resp[160];

  if (at_tx(fd, "ATE0", resp, sizeof(resp), 500, 800, 0) <= 0 ||
      !resp_ok(resp) || resp_fail(resp)) {
    printf("[ew-at] echo setup failed\n");
    return -1;
  }
  if (at_tx(fd, "AT+CWMODE=1", resp, sizeof(resp), 800, 1500, 0) <= 0 ||
      !resp_ok(resp) || resp_fail(resp)) {
    printf("[ew-at] station setup failed\n");
    return -1;
  }
  return 0;
}

/* 轻量握手：扫描/查询用，失败时不 RST（避免扫到一半被复位）。 */
static int at_wake_light(int fd)
{
  if (sync_baud(fd) != 0) {
    return -1;
  }
  return at_station_setup(fd);
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
#if EW_AT_BAUD_FIXED
      printf("[ew-at] no AT reply at fixed 115200 after bounded recovery\n");
#else
      printf("[ew-at] no AT reply at supported baud rates after bounded recovery\n");
#endif
      fflush(stdout);
      return -1;
    }
  }

  if (at_station_setup(fd) != 0) {
    return -1;
  }
  printf("[ew-at] wake ok @%u baud\n", k_baud_name[g_baud_idx]);
  fflush(stdout);
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

/* +CIPSTA:ip:"192.168.1.23" 或 +CIFSR:STAIP,"192.168.1.23" → ip。0 = 有效地址。 */
static int parse_staip(const char *resp, char *ip, unsigned ip_sz)
{
  const char *p;

  if (ip_sz > 0) {
    ip[0] = '\0';
  }
  if (resp == NULL) {
    return -1;
  }
  p = strstr(resp, "+CIPSTA:ip:");
  if (p != NULL) {
    if (copy_quoted(p + 12, ip, ip_sz) == NULL) {
      return -1;
    }
  } else {
    p = strstr(resp, "STAIP,");
    if (p == NULL) {
      return -1;
    }
    if (copy_quoted(p + 6, ip, ip_sz) == NULL) {
      return -1;
    }
  }
  if (ip[0] == '\0' || strcmp(ip, "0.0.0.0") == 0) {
    return -1;
  }
  return 0;
}

/* 优先 CIPSTA?（官方 DHCP 查询），回退 CIFSR */
static int query_sta_ip(int fd, char *ip, unsigned ip_sz)
{
  char resp[384];

  if (ip != NULL && ip_sz > 0) {
    ip[0] = '\0';
  }
  (void)at_tx(fd, "AT+CIPSTA?", resp, sizeof(resp), 1500, 4000, 0);
  if (parse_staip(resp, ip, ip_sz) == 0) {
    return 0;
  }
  (void)at_tx(fd, "AT+CIFSR", resp, sizeof(resp), 1500, 4000, 0);
  return parse_staip(resp, ip, ip_sz);
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
  static char scan_buf[16384];
  int fd;
  int n;
  size_t len;
  int is_cwlap;

  if (at_line == NULL || at_line[0] == '\0') {
    at_line = "AT";
  }
  snprintf(line, sizeof(line), "%s", at_line);
  len = strlen(line);
  while (len > 0 && (line[len - 1] == '\r' || line[len - 1] == '\n')) {
    line[--len] = '\0';
  }
  is_cwlap = (strstr(line, "CWLAP") != NULL);

  fd = at_begin();
  if (fd < 0) {
    return 1;
  }
  if (at_wake_light(fd) != 0 && at_wake(fd) != 0) {
    at_end(fd);
    printf("[ew-at] no reply (wake fail)\n");
    return 3;
  }

  if (is_cwlap) {
    char tx[192];
    int m;

    tcflush(fd, TCIFLUSH);
    printf("[ew-at] tx=%s (long read)\n", line);
    fflush(stdout);
    m = snprintf(tx, sizeof(tx), "%s\r\n", line);
    if (m > 0) {
      (void)write_all(fd, tx, (unsigned)m);
    }
    memset(scan_buf, 0, sizeof(scan_buf));
    n = at_read_scan(fd, scan_buf, sizeof(scan_buf), 55000);
    if (n > 0) {
      printf("[ew-at] CWLAP raw bytes=%d markers=%d\n",
             n, scan_count_markers(scan_buf));
      print_rx_blob(scan_buf, n);
    }
    at_drain_rx(fd, 400);
  } else {
    n = at_tx(fd, line, resp, sizeof(resp), 2500, 8000, 0);
    print_rx(resp);
  }
  at_end(fd);

  if (is_cwlap) {
    if (n > 0 && resp_ok(scan_buf)) {
      return 0;
    }
    if (n <= 0) {
      printf("[ew-at] no reply\n");
    }
    return (n > 0) ? 2 : 3;
  }

  if (n > 0 && (resp_ok(resp) || resp_got_ip(resp) || resp_wifi_connected(resp))) {
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

/* 分层探测：MODEM → WiFi → LAN(IP) → ONLINE，对应排查清单 D10 */
int ew_wifi_at_diag(void)
{
  char resp[384];
  char ip[24];
  int fd;

  fd = at_begin();
  if (fd < 0) {
    printf("[ew-wifi] MODEM: not responding\n");
    return 1;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    printf("[ew-wifi] MODEM: not responding\n");
    return 1;
  }
  printf("[ew-wifi] MODEM: OK\n");

  (void)at_tx(fd, "AT+CWJAP?", resp, sizeof(resp), 1500, 4000, 0);
  print_rx(resp);
  if (strstr(resp, "No AP") != NULL || strstr(resp, "NULL") != NULL) {
    printf("[ew-wifi] WIFI: not connected\n");
    at_end(fd);
    return 0;
  }
  if (resp_wifi_connected(resp) || strstr(resp, "+CWJAP:") != NULL) {
    printf("[ew-wifi] WIFI: connected\n");
  }

  if (query_sta_ip(fd, ip, sizeof(ip)) != 0) {
    printf("[ew-wifi] LAN: no IP\n");
    at_end(fd);
    return 0;
  }
  printf("[ew-wifi] LAN: ip=%s\n", ip);

  if (inet_probe(fd) == 0) {
    printf("[ew-wifi] Network: ONLINE\n");
  } else {
    printf("[ew-wifi] Network: LAN ONLY\n");
  }
  at_end(fd);
  return 0;
}

int ew_wifi_at_status(void)
{
  int rc = 0;

  printf("[ew-at] --- status ---\n");
  if (ew_wifi_at_cmd("AT+GMR") != 0) {
    rc = 2;
  }
  if (ew_wifi_at_cmd("AT+CWMODE?") != 0) {
    rc = 2;
  }
  if (ew_wifi_at_cmd("AT+CWJAP?") != 0) {
    rc = 2;
  }
  if (ew_wifi_at_cmd("AT+CIPSTA?") != 0) {
    rc = 2;
  }
  return rc;
}

/* 已持有串口时的公网探测：0 = 通。DNS 回退避免运营商屏蔽 ICMP 时误报。 */
static int inet_probe(int fd)
{
  char cmd[96];
  char resp[192];
  int n;

  n = at_tx(fd, "AT+PING=\"" EW_WIFI_PING_HOST "\"", resp, sizeof(resp),
            5000, 8000, 0);
  if (n > 0 && strstr(resp, "+PING:") != NULL && !resp_fail(resp)) {
    printf("[ew-wifi] inet probe: ICMP OK\n");
    return 0;
  }

  snprintf(cmd, sizeof(cmd), "AT+CIPDOMAIN=\"%s\"", EW_WIFI_DNS_HOST);
  n = at_tx(fd, cmd, resp, sizeof(resp), 5000, 8000, 0);
  if (n > 0 && strstr(resp, "+CIPDOMAIN:") != NULL &&
      resp_ok(resp) && !resp_fail(resp)) {
    printf("[ew-wifi] inet probe: ICMP blocked, DNS OK\n");
    return 0;
  }
  printf("[ew-wifi] inet probe: ICMP and DNS failed\n");
  return -1;
}

ew_wifi_state_t ew_wifi_probe(int check_inet, char *ip, unsigned ip_sz)
{
  char resp[384];
  char addr[24];
  ew_wifi_state_t st;
  int fd;

  if (ip != NULL && ip_sz > 0) {
    ip[0] = '\0';
  }

  fd = at_begin();
  if (fd < 0) {
    if (errno == EBUSY) {
      /* Contention is not evidence of a disconnected modem. */
      ew_net_state_error(EW_NET_ERR_AT_BUSY);
    } else {
      ew_net_state_publish(EW_NET_LINK_DOWN, NULL);
      ew_net_state_error(EW_NET_ERR_RESPONSE);
    }
    return EW_WIFI_DOWN;
  }
  if (at_wake_light(fd) != 0) {
    at_end(fd);
    ew_net_state_publish(EW_NET_LINK_DOWN, NULL);
    return EW_WIFI_DOWN;
  }

  /* Association and DHCP must agree. A stale non-zero CIPSTA address alone
   * must never make the UI report a live link. */
  (void)at_tx(fd, "AT+CWJAP?", resp, sizeof(resp), 1500, 4000, 0);
  if (strstr(resp, "+CWJAP:") == NULL ||
      strstr(resp, "No AP") != NULL || strstr(resp, "NULL") != NULL ||
      resp_fail(resp)) {
    at_end(fd);
    ew_net_state_publish(EW_NET_LINK_IDLE, NULL);
    return EW_WIFI_IDLE;
  }

  if (query_sta_ip(fd, addr, sizeof(addr)) != 0) {
    at_end(fd);
    ew_net_state_publish(EW_NET_LINK_IDLE, NULL);
    return EW_WIFI_IDLE;
  }

  st = EW_WIFI_JOINED;
  if (check_inet && inet_probe(fd) == 0) {
    st = EW_WIFI_ONLINE;
  }
  at_end(fd);

  if (ip != NULL && ip_sz > 0) {
    snprintf(ip, ip_sz, "%s", addr);
  }
  ew_net_state_publish(st == EW_WIFI_ONLINE ? EW_NET_LINK_ONLINE
                                            : EW_NET_LINK_JOINED,
                       addr);
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
  char *end;
  long ecn;
  long rssi;
  unsigned len = 0;

  if (line == NULL || ap == NULL) {
    return -1;
  }
  p = strstr(line, "+CWLAP:");
  if (p == NULL) {
    return -1;
  }
  p += 7;
  while (*p == ' ' || *p == '\t') {
    p++;
  }
  if (*p++ != '(' || *p < '0' || *p > '9') {
    return -1;
  }
  ecn = strtol(p, &end, 10);
  if (ecn < 0 || ecn > 14 || *end != ',' || end[1] != '"') {
    return -1;
  }
  memset(ap, 0, sizeof(*ap));
  ap->open = (ecn == 0);
  q = end + 2;
  while (*q != '\0' && *q != '"') {
    if (*q == '\\') {
      q++;
      if (*q == '\0') {
        return -1;
      }
    }
    if (len + 1 >= sizeof(ap->ssid)) {
      return -1;
    }
    ap->ssid[len++] = *q++;
  }
  /* A hidden SSID cannot be selected by name; use manual entry. */
  if (len == 0 || *q != '"' || q[1] != ',') {
    return -1;
  }
  q += 2;
  p = (*q == '-') ? q + 1 : q;
  if (*p < '0' || *p > '9') {
    return -1;
  }
  rssi = strtol(q, &end, 10);
  if (rssi > 0 || rssi < -120 || (*end != ',' && *end != ')')) {
    return -1;
  }
  p = line + strlen(line);
  while (p > line && (p[-1] == ' ' || p[-1] == '\r' || p[-1] == '\n')) {
    p--;
  }
  if (p == line || p[-1] != ')') {
    return -1;
  }
  ap->rssi = (int)rssi;
  return 0;
}

static int scan_from_buf(const char *buf, ew_wifi_ap_t *aps, int max, int *count)
{
  const char *p;
  char line[384];
  int ok = 0;
  int fail = 0;

  if (buf == NULL || aps == NULL || count == NULL) {
    return -1;
  }
  for (p = buf; (p = strstr(p, "+CWLAP:")) != NULL; ) {
    ew_wifi_ap_t ap;
    const char *eol = strpbrk(p, "\r\n");
    unsigned len;
    const char *src = p;

    if (eol != NULL) {
      len = (unsigned)(eol - p);
      p = eol + 1;
      if (*eol == '\r' && *p == '\n') {
        p++;
      }
    } else {
      len = (unsigned)strlen(p);
      p += len;
    }
    if (len >= sizeof(line)) {
      len = sizeof(line) - 1;
    }
    memcpy(line, src, len);
    line[len] = '\0';
    if (scan_parse_line(line, &ap) == 0) {
      scan_insert_ap(aps, max, count, &ap);
      ok++;
      if (ok <= 4) {
        printf("[ESP-AT PARSE] ssid=%s rssi=%d\n", ap.ssid, ap.rssi);
        fflush(stdout);
      }
    } else {
      fail++;
      if (fail <= 2) {
        printf("[ew-at] CWLAP parse skip: %.96s\n", line);
        fflush(stdout);
      }
    }
  }
  if (fail > 0) {
    printf("[ew-at] CWLAP parse ok=%d fail=%d\n", ok, fail);
    fflush(stdout);
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

static int scan_tx_cwlap(int fd, const char *cmd, char *buf, unsigned bufsz)
{
  char tx[64];
  int m;

  if (cmd == NULL || cmd[0] == '\0') {
    cmd = "AT+CWLAP";
  }
  tcflush(fd, TCIFLUSH);
  memset(buf, 0, bufsz);
  m = snprintf(tx, sizeof(tx), "%s", cmd);
  if (m <= 0 || (unsigned)m >= sizeof(tx)) {
    return -1;
  }
  printf("[ew-at] tx=%s (scan read)\n", cmd);
  fflush(stdout);
  if (write_all(fd, tx, (unsigned)m) != 0) {
    return -1;
  }
  if (write_all(fd, "\r\n", 2) != 0) {
    return -1;
  }
  return at_read_scan(fd, buf, bufsz, 55000);
}

/* 单次标准 CWLAP，使用模组默认字段以保持固件兼容性。 */
static int scan_run_once(int fd, ew_wifi_ap_t *aps, int max, int *count)
{
  static char buf[16384];
  int n;
  int before = *count;
  int markers;

  n = scan_tx_cwlap(fd, "AT+CWLAP", buf, sizeof(buf));
  if (n <= 0) {
    printf("[ew-at] CWLAP no reply (n=%d)\n", n);
    at_drain_rx(fd, 800);
    return -1;
  }
  if (resp_fail(buf)) {
    printf("[ew-at] CWLAP rejected by modem\n");
    print_rx(buf);
    return -1;
  }
  markers = scan_count_markers(buf);
  scan_from_buf(buf, aps, max, count);
  printf("[ew-at] CWLAP bytes=%d markers=%d parsed=%d (+%d)\n",
         n, markers, *count, *count - before);
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
    at_drain_rx(fd, 800);
    return -1;
  }
  if (resp_fail(buf)) {
    printf("[ew-at] CWLAP target rejected by modem\n");
    print_rx(buf);
    return -1;
  }
  scan_from_buf(buf, aps, max, count);
  printf("[ew-at] CWLAP target \"%s\" markers=%d parsed=%d\n",
         ssid, scan_count_markers(buf), *count);
  fflush(stdout);
  return *count;
}

void ew_wifi_scan_hint_clear(void)
{
  pthread_mutex_lock(&g_scan_state_mu);
  g_scan_hint_n = 0;
  memset(g_scan_hints, 0, sizeof(g_scan_hints));
  pthread_mutex_unlock(&g_scan_state_mu);
}

int ew_wifi_scan_hint_add(const char *ssid)
{
  int i;

  if (ssid == NULL || ssid[0] == '\0') {
    return -1;
  }
  pthread_mutex_lock(&g_scan_state_mu);
  for (i = 0; i < g_scan_hint_n; i++) {
    if (strcmp(g_scan_hints[i], ssid) == 0) {
      pthread_mutex_unlock(&g_scan_state_mu);
      return 0;
    }
  }
  if (g_scan_hint_n >= EW_WIFI_HINT_MAX) {
    pthread_mutex_unlock(&g_scan_state_mu);
    return -1;
  }
  snprintf(g_scan_hints[g_scan_hint_n], EW_WIFI_SSID_MAX, "%s", ssid);
  g_scan_hint_n++;
  pthread_mutex_unlock(&g_scan_state_mu);
  return 0;
}

static int scan_target_listed(const char *ssid, ew_wifi_ap_t *aps, int count)
{
  int i;

  for (i = 0; i < count; i++) {
    if (strcmp(aps[i].ssid, ssid) == 0) {
      return 1;
    }
  }
  return 0;
}

static void scan_directed_all(int fd, ew_wifi_ap_t *aps, int max, int *count)
{
  char saved_ssid[EW_WIFI_SSID_MAX];
  char hints[EW_WIFI_HINT_MAX][EW_WIFI_SSID_MAX];
  const char *targets[EW_WIFI_HINT_MAX + 1];
  int target_n = 0;
  int hint_n;
  int i;
  int t;

  if (ew_wifi_cred_load(saved_ssid, sizeof(saved_ssid), NULL, 0) == 0) {
    targets[target_n++] = saved_ssid;
  }
  pthread_mutex_lock(&g_scan_state_mu);
  hint_n = g_scan_hint_n;
  memcpy(hints, g_scan_hints, sizeof(hints));
  pthread_mutex_unlock(&g_scan_state_mu);

  for (i = 0; i < hint_n; i++) {
    int dup = 0;

    for (t = 0; t < target_n; t++) {
      if (strcmp(targets[t], hints[i]) == 0) {
        dup = 1;
        break;
      }
    }
    if (!dup && target_n < EW_WIFI_HINT_MAX + 1) {
      targets[target_n++] = hints[i];
    }
  }

  for (t = 0; t < target_n; t++) {
    if (scan_target_listed(targets[t], aps, *count)) {
      continue;
    }
    (void)scan_target_ssid(fd, targets[t], aps, max, count);
  }
}

int ew_wifi_probe_ssid(const char *ssid, ew_wifi_ap_t *ap)
{
  ew_wifi_ap_t scratch[EW_WIFI_SCAN_MAX];
  int count = 0;
  int fd;

  if (ssid == NULL || ssid[0] == '\0' || ap == NULL) {
    return -1;
  }
  memset(ap, 0, sizeof(*ap));

  fd = at_begin();
  if (fd < 0) {
    return -1;
  }
  if (at_wake_light(fd) != 0 && at_wake(fd) != 0) {
    at_end(fd);
    return -1;
  }
  if (scan_target_ssid(fd, ssid, scratch, EW_WIFI_SCAN_MAX, &count) < 0 ||
      count <= 0) {
    at_end(fd);
    return -1;
  }
  *ap = scratch[0];
  at_end(fd);
  return 0;
}

int ew_wifi_scan(ew_wifi_ap_t *aps, int max)
{
  char resp[160];
  int count = 0;
  int fd = -1;
  int scan_rc;
  int cached;
  int result = EW_WIFI_SCAN_ERROR;

  if (aps == NULL || max <= 0) {
    return EW_WIFI_SCAN_ERROR;
  }

  cached = scan_cache_copy(aps, max, 0);
  if (cached >= 0) {
    printf("[ew-at] scan cache %d ap\n", cached);
    return cached;
  }

  if (pthread_mutex_trylock(&g_scan_mu) != 0) {
    cached = scan_cache_copy(aps, max, 1);
    if (cached >= 0) {
      printf("[ew-at] scan busy; return cached %d ap\n", cached);
      return cached;
    }
    printf("[ew-at] scan busy\n");
    return EW_WIFI_SCAN_BUSY;
  }

  fd = at_begin();
  if (fd < 0) {
    if (errno == EBUSY) {
      result = EW_WIFI_SCAN_BUSY;
    }
    goto done;
  }
  if (at_wake_light(fd) != 0) {
    /* 轻量握手失败再试完整 wake（含 RST） */
    if (at_wake(fd) != 0) {
      goto done;
    }
  }

  /* Station 模式允许保持连接时扫描，不得 CWQAP 断开刚建立的链路。 */
  (void)at_tx(fd, "AT+SLEEP=0", resp, sizeof(resp), 800, 1500, 0);
  (void)at_tx(fd, "AT+CWCOUNTRY=1,\"CN\",1,13", resp, sizeof(resp),
              800, 1500, 0);
  if (!resp_ok(resp)) {
    printf("[ew-at] country setup failed; scan channel coverage unconfirmed\n");
    print_rx(resp);
  }
  /* Request only ECN, SSID and RSSI. This bounds UART traffic without
   * changing the parser-visible prefix used by supported ESP-AT releases. */
  (void)at_tx(fd, "AT+CWLAPOPT=1,7", resp, sizeof(resp), 800, 1500, 0);
  usleep(500000);

  scan_rc = scan_run_once(fd, aps, max, &count);
  if (scan_rc < 0) {
    at_drain_rx(fd, 400);
    goto done;
  }

  /* Supplement the scan with saved and manually entered SSIDs. */
  scan_directed_all(fd, aps, max, &count);

  scan_sort_rssi(aps, count);
  scan_cache_store(aps, count);
  at_drain_rx(fd, 400);

  printf("[ew-at] scan found %d ap\n", count);
  fflush(stdout);
  result = count;

done:
  if (fd >= 0) {
    at_end(fd);
  }
  pthread_mutex_unlock(&g_scan_mu);
  return result;
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

  /* ESP-AT persists station configuration only when SYSSTORE is enabled.
   * Older firmware may reject SYSSTORE; keep Join compatible but log it. */
  n = at_tx(fd, "AT+SYSSTORE=1", resp, sizeof(resp), 800, 1500, 0);
  if (n <= 0 || resp_fail(resp)) {
    printf("[ew-at] SYSSTORE unsupported; module persistence unconfirmed\n");
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
    printf("[ew-at] join %s: %s (connected=%d got_ip=%d)\n", ssid, why,
           resp_wifi_connected(resp), resp_got_ip(resp));
    return 3;
  }
  if (resp_wifi_connected(resp)) {
    printf("[ew-at] join: WIFI CONNECTED\n");
  }
  if (resp_got_ip(resp)) {
    printf("[ew-at] join: WIFI GOT IP\n");
  }

  n = at_tx(fd, "AT+CWAUTOCONN=1", resp, sizeof(resp), 800, 1500, 0);
  if (n <= 0 || resp_fail(resp)) {
    printf("[ew-at] CWAUTOCONN enable failed\n");
  }

  if (query_sta_ip(fd, addr, sizeof(addr)) != 0) {
    snprintf(addr, sizeof(addr), "?");
  }
  online = (inet_probe(fd) == 0);
  at_end(fd);

  (void)cred_save(ssid, pass);
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, online ? "WIFI ON %s" : "WIFI LAN %s", addr);
  }
  printf("[ew-at] join %s ok ip=%s inet=%d\n", ssid, addr, online);
  ew_net_state_publish(online ? EW_NET_LINK_ONLINE : EW_NET_LINK_JOINED, addr);
  fflush(stdout);
  return 0;
}

int ew_wifi_forget(void)
{
  char resp[256];
  char ip[24];
  int fd;
  int n;

  fd = at_begin();
  if (fd < 0) {
    printf("[ew-at] forget failed: modem busy/unavailable\n");
    return 1;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    printf("[ew-at] forget failed: wake failed\n");
    return 2;
  }

  n = at_tx(fd, "AT+CWAUTOCONN=0", resp, sizeof(resp), 800, 1500, 0);
  if (n <= 0 || !resp_ok(resp) || resp_fail(resp)) {
    at_end(fd);
    printf("[ew-at] forget failed: could not disable auto-connect\n");
    return 3;
  }

  n = at_tx(fd, "AT+CWQAP", resp, sizeof(resp), 1500, 4000, 0);
  print_rx(resp);
  if (n <= 0 || !resp_ok(resp) || resp_fail(resp)) {
    at_end(fd);
    printf("[ew-at] forget failed: CWQAP rejected\n");
    return 4;
  }

  /* Do not report success or erase credentials while the station still has IP. */
  usleep(300000);
  if (query_sta_ip(fd, ip, sizeof(ip)) == 0) {
    at_end(fd);
    printf("[ew-at] forget failed: still connected ip=%s\n", ip);
    return 5;
  }
  at_end(fd);

  if (unlink(EW_WIFI_CONF) != 0 && errno != ENOENT) {
    printf("[ew-at] forget failed: unlink errno=%d\n", errno);
    return 6;
  }
  printf("[ew-at] disconnected; credentials cleared\n");
  ew_net_state_publish(EW_NET_LINK_IDLE, NULL);
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
  st = ew_wifi_probe(0, ip, sizeof(ip));
  if (st == EW_WIFI_DOWN) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "NO MODEM");
    }
    return 2;
  }
  if (st != EW_WIFI_IDLE) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "WIFI LAN %s", ip);
    }
    printf("[ew-at] already joined ip=%s\n", ip);
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

ew_wifi_http_result_t ew_wifi_http_ssl_post(const char *host, unsigned port,
                                            const char *path,
                                            const char *api_key,
                                            const char *json_body,
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
    return EW_WIFI_HTTP_INVALID;
  }
  if (port == 0) {
    port = 443;
  }

  hlen = (unsigned)snprintf(http, sizeof(http),
                            "POST %s HTTP/1.1\r\n"
                            "Host: %s\r\n"
                            "api-key: %s\r\n"
                            "Content-Type: application/json\r\n"
                            "Connection: close\r\n"
                            "Content-Length: %u\r\n"
                            "\r\n"
                            "%s",
                            path, host, api_key ? api_key : "",
                            (unsigned)strlen(json_body), json_body);
  if (hlen >= sizeof(http) - 1) {
    printf("[ew-at] http too long\n");
    return EW_WIFI_HTTP_INVALID;
  }

  dst = (resp != NULL && resp_sz > 8) ? resp : scratch;
  dst_sz = (resp != NULL && resp_sz > 8) ? resp_sz : sizeof(scratch);
  dst[0] = '\0';

  fd = at_begin();
  if (fd < 0) {
    return EW_WIFI_HTTP_AT_BUSY;
  }
  if (at_wake(fd) != 0) {
    at_end(fd);
    printf("[ew-at] http: modem down\n");
    return EW_WIFI_HTTP_MODEM_DOWN;
  }

  (void)at_tx(fd, "AT+CIPMUX=0", scratch, sizeof(scratch), 800, 1500, 0);
  (void)at_tx(fd, "AT+CIPMODE=0", scratch, sizeof(scratch), 800, 1500, 0);
  (void)at_tx(fd, "AT+CIPCLOSE", scratch, sizeof(scratch), 800, 1500, 0);
  n = at_tx(fd, "AT+CIPSSLCCONF=0", scratch, sizeof(scratch), 800, 1500, 0);
  if (n <= 0 || !resp_ok(scratch) || resp_fail(scratch)) {
    print_rx(scratch);
    at_end(fd);
    printf("[ew-at] SSL client config fail\n");
    return EW_WIFI_HTTP_TLS;
  }

  /* MiMo/CDN requires TLS SNI; without it ESP-AT returns ERROR at CIPSTART. */
  snprintf(cmd, sizeof(cmd), "AT+CIPSSLCSNI=\"%s\"", host);
  n = at_tx(fd, cmd, scratch, sizeof(scratch), 800, 2000, 0);
  if (n <= 0 || !resp_ok(scratch) || resp_fail(scratch)) {
    print_rx(scratch);
    at_end(fd);
    printf("[ew-at] SSL SNI config fail\n");
    return EW_WIFI_HTTP_TLS;
  }

  snprintf(cmd, sizeof(cmd), "AT+CIPSTART=\"SSL\",\"%s\",%u", host, port);
  n = at_tx(fd, cmd, scratch, sizeof(scratch), 30000, 35000, 0);
  if (n <= 0 || resp_fail(scratch) ||
      (strstr(scratch, "CONNECT") == NULL && !resp_ok(scratch))) {
    print_rx(scratch);
    at_end(fd);
    printf("[ew-at] SSL CIPSTART fail\n");
    return n <= 0 ? EW_WIFI_HTTP_TIMEOUT : EW_WIFI_HTTP_TLS;
  }

  snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%u", hlen);
  (void)at_tx(fd, cmd, scratch, sizeof(scratch), 1500, 2000, 0);
  if (strchr(scratch, '>') == NULL && wait_prompt(fd, 3000) != 0) {
    at_end(fd);
    printf("[ew-at] CIPSEND no prompt\n");
    return EW_WIFI_HTTP_TIMEOUT;
  }

  if (write_all(fd, http, hlen) != 0) {
    at_end(fd);
    printf("[ew-at] http body write stalled\n");
    return EW_WIFI_HTTP_SEND;
  }
  n = collect_body(fd, dst, dst_sz, 25000);
  (void)at_tx(fd, "AT+CIPCLOSE", scratch, sizeof(scratch), 800, 1500, 0);
  at_end(fd);

  printf("[ew-at] http bytes=%d\n", n);
  return (n > 16) ? EW_WIFI_HTTP_OK : EW_WIFI_HTTP_TIMEOUT;
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

int ew_wifi_at_diag(void)
{
  printf("[ew-at] host stub diag\n");
  return 0;
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

void ew_wifi_scan_hint_clear(void)
{
}

int ew_wifi_scan_hint_add(const char *ssid)
{
  (void)ssid;
  return 0;
}

int ew_wifi_scan(ew_wifi_ap_t *aps, int max)
{
  (void)aps;
  (void)max;
  return 0;
}

int ew_wifi_probe_ssid(const char *ssid, ew_wifi_ap_t *ap)
{
  (void)ssid;
  (void)ap;
  return -1;
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

ew_wifi_http_result_t ew_wifi_http_ssl_post(const char *host, unsigned port,
                                            const char *path,
                                            const char *api_key,
                                            const char *json_body,
                                            char *resp, unsigned resp_sz)
{
  (void)host;
  (void)port;
  (void)path;
  (void)api_key;
  (void)json_body;
  if (resp != NULL && resp_sz > 0) {
    snprintf(resp, resp_sz, "host stub");
  }
  return EW_WIFI_HTTP_MODEM_DOWN;
}

#endif /* __NuttX__ */
