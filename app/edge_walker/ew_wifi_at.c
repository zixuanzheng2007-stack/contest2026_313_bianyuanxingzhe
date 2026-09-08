/****************************************************************************
 * UART AT 猫：PA24/PA25 → /dev/ttyS2 @ 115200
 * 无 SSID 时走 ESP-Touch SmartConfig（用乐鑫 Esptouch 配网）
 *
 * 本地可选 ew_wifi_secret.h（已 gitignore）提供 EW_WIFI_SSID / EW_WIFI_PASS。
 * 仓内默认空 SSID：只测 AT，不提交密码。
 ****************************************************************************/

#include "ew_wifi_at.h"

#include <stdio.h>
#include <string.h>
#include <errno.h>

#if defined(__has_include)
#if __has_include("ew_wifi_secret.h")
#include "ew_wifi_secret.h"
#endif
#endif
#ifndef EW_WIFI_SSID
#define EW_WIFI_SSID ""
#endif
#ifndef EW_WIFI_PASS
#define EW_WIFI_PASS ""
#endif

#ifdef __NuttX__
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <nuttx/config.h>
#endif

#ifdef __NuttX__
static int uart_open(void)
{
  struct termios tio;
  int fd;

  fd = open(EW_WIFI_AT_DEV, O_RDWR | O_NOCTTY);
  if (fd < 0) {
    printf("[ew-at] open %s failed errno=%d\n", EW_WIFI_AT_DEV, errno);
    return -1;
  }

  if (tcgetattr(fd, &tio) == 0) {
    cfmakeraw(&tio);
    cfsetispeed(&tio, B115200);
    cfsetospeed(&tio, B115200);
    tio.c_cflag |= (CLOCAL | CREAD);
    tio.c_cc[VMIN] = 0;
    tio.c_cc[VTIME] = 1;
    tcsetattr(fd, TCSANOW, &tio);
  }
  tcflush(fd, TCIOFLUSH);
  return fd;
}

static int resp_fail(const char *s)
{
  return strstr(s, "ERROR") != NULL || strstr(s, "FAIL") != NULL;
}

static int resp_ok(const char *s)
{
  return strstr(s, "OK") != NULL;
}

static int resp_got_ip(const char *s)
{
  return strstr(s, "WIFI GOT IP") != NULL ||
         strstr(s, "GOT IP") != NULL ||
         strstr(s, "smartconfig connected") != NULL;
}

static int read_until(int fd, char *out, unsigned out_sz, int timeout_ms, int want_ip)
{
  unsigned n = 0;
  int waited = 0;

  if (out_sz == 0) {
    return -1;
  }
  out[0] = '\0';
  while (waited < timeout_ms && n + 1 < out_sz) {
    char c;
    int r = read(fd, &c, 1);
    if (r == 1) {
      out[n++] = c;
      out[n] = '\0';
      if (resp_got_ip(out)) {
        return (int)n;
      }
      if (resp_fail(out)) {
        return (int)n;
      }
      if (!want_ip && resp_ok(out)) {
        return (int)n;
      }
      waited = 0;
    } else {
      usleep(20000);
      waited += 20;
    }
  }
  return (int)n;
}

static int at_tx(int fd, const char *line, char *resp, unsigned resp_sz,
                 int timeout_ms, int want_ip)
{
  char tx[192];
  int m;

  m = snprintf(tx, sizeof(tx), "%s\r\n", line);
  if (m > 0) {
    (void)write(fd, tx, (size_t)m);
  }
  if (strstr(line, "CWJAP") != NULL) {
    printf("[ew-at] tx=AT+CWJAP=***\n");
  } else {
    printf("[ew-at] tx=%s\n", line);
  }
  fflush(stdout);
  return read_until(fd, resp, resp_sz, timeout_ms, want_ip);
}

int ew_wifi_at_cmd(const char *at_line)
{
  char line[160];
  char resp[256];
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

  fd = uart_open();
  if (fd < 0) {
    return 1;
  }
  n = at_tx(fd, line, resp, sizeof(resp), 1500, 0);
  close(fd);
  if (n > 0) {
    printf("[ew-at] rx=%s\n", resp);
    return (resp_ok(resp) || resp_got_ip(resp)) ? 0 : 2;
  }
  printf("[ew-at] no reply\n");
  return 3;
}

int ew_wifi_at_ping(void)
{
  return ew_wifi_at_cmd("AT");
}

int ew_wifi_bringup(char *out, unsigned out_sz)
{
  char resp[320];
  char jap[192];
  int fd;
  int n;

  if (out != NULL && out_sz > 0) {
    out[0] = '\0';
  }

  fd = uart_open();
  if (fd < 0) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "AT NODEV");
    }
    return 1;
  }

  (void)at_tx(fd, "AT", resp, sizeof(resp), 800, 0);
  n = at_tx(fd, "AT", resp, sizeof(resp), 1500, 0);
  if (n <= 0 || !resp_ok(resp)) {
    close(fd);
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "AT FAIL");
    }
    printf("[ew-at] ping fail\n");
    return 2;
  }

  (void)at_tx(fd, "ATE0", resp, sizeof(resp), 800, 0);
  (void)at_tx(fd, "AT+CWMODE=1", resp, sizeof(resp), 1500, 0);

  if (EW_WIFI_SSID[0] != '\0') {
    snprintf(jap, sizeof(jap), "AT+CWJAP=\"%s\",\"%s\"", EW_WIFI_SSID, EW_WIFI_PASS);
    n = at_tx(fd, jap, resp, sizeof(resp), 20000, 1);
    close(fd);
    if (n > 0 && (resp_got_ip(resp) || resp_ok(resp)) && !resp_fail(resp)) {
      if (out != NULL && out_sz > 0) {
        snprintf(out, out_sz, "WIFI OK");
      }
      printf("[ew-at] join ok\n");
      return 0;
    }
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "WIFI FAIL");
    }
    printf("[ew-at] join fail\n");
    return 3;
  }

  n = at_tx(fd, "AT+CWSTARTSMART=3", resp, sizeof(resp), 2000, 0);
  if (n <= 0 || !resp_ok(resp)) {
    close(fd);
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "AT OK");
    }
    printf("[ew-at] smart start fail, AT still ok\n");
    return 0;
  }

  n = read_until(fd, resp, sizeof(resp), 40000, 1);
  (void)at_tx(fd, "AT+CWSTOPSMART", resp, sizeof(resp), 1500, 0);
  close(fd);

  if (n > 0 && resp_got_ip(resp)) {
    if (out != NULL && out_sz > 0) {
      snprintf(out, out_sz, "WIFI OK");
    }
    printf("[ew-at] smart ok\n");
    return 0;
  }
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, "AT OK");
  }
  printf("[ew-at] smart timeout, AT ok\n");
  return 0;
}

#else

int ew_wifi_at_cmd(const char *at_line)
{
  printf("[ew-at] host stub cmd=%s\n", at_line ? at_line : "AT");
  return 0;
}

int ew_wifi_at_ping(void)
{
  return ew_wifi_at_cmd("AT");
}

int ew_wifi_bringup(char *out, unsigned out_sz)
{
  if (out != NULL && out_sz > 0) {
    snprintf(out, out_sz, "AT STUB");
  }
  return 0;
}

#endif
