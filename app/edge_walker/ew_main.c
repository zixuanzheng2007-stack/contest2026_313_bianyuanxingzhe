/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 边缘行者主程序（郑子轩）
 *
 * 用法见 `ew help`。板子上由 rcS 启动 `ew boot`，其余子命令只用于台架调试。
 ****************************************************************************/

#include "alert_output.h"
#include "alert_buzzer.h"
#include "alert_lcd.h"
#include "ew_chat.h"
#include "ew_ld2451.h"
#include "ew_llm.h"
#include "ew_wifi_at.h"
#include "ew_agent.h"
#include "ew_safety.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __NuttX__
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#endif

static int cmd_alert(int argc, char **argv)
{
  ew_alert_level_t level = EW_ALERT_SOFT;
  const char *reason = "manual_test";

  if (argc >= 3) {
    if (strcmp(argv[2], "none") == 0 || strcmp(argv[2], "0") == 0) {
      level = EW_ALERT_NONE;
    } else if (strcmp(argv[2], "strong") == 0 || strcmp(argv[2], "2") == 0) {
      level = EW_ALERT_STRONG;
    } else if (strcmp(argv[2], "crit") == 0 || strcmp(argv[2], "3") == 0) {
      level = EW_ALERT_EMERGENCY;
    } else if (strcmp(argv[2], "soft") == 0 || strcmp(argv[2], "1") == 0) {
      level = EW_ALERT_SOFT;
    } else if (strcmp(argv[2], "emergency") == 0) {
      level = EW_ALERT_EMERGENCY;
    } else {
      printf("[ew] invalid alert level\n");
      return 1;
    }
  }
  if (argc >= 4) {
    reason = argv[3];
  }

  {
    ew_decision_t decision = {0};
    decision.level = level;
    decision.ttc_s = -1.0f;
    decision.reason = reason;
    return ew_agent_emit_decision(&decision, EW_EVENT_SOURCE_MANUAL);
  }
}

static int cmd_buzz(int argc, char **argv)
{
  unsigned freq = (argc >= 3) ? (unsigned)atoi(argv[2]) : 2500u;
  unsigned ms = (argc >= 4) ? (unsigned)atoi(argv[3]) : 800u;

  printf("[ew] buzz PA28 (40P.23)\n");
  return alert_buzzer_beep(freq, ms);
}

static int cmd_screen(int argc, char **argv)
{
  if (argc >= 3 && strcmp(argv[2], "info") == 0) {
    return alert_lcd_info();
  }
  return alert_lcd_selftest();
}

static int cmd_fake(int argc, char **argv)
{
  ew_track_t t;
  ew_decision_t d;

  memset(&t, 0, sizeof(t));
  t.valid = true;
  t.range_m = (argc >= 3) ? (float)atof(argv[2]) : 10.0f;
  t.speed_kmh = (argc >= 4) ? (float)atof(argv[3]) : 20.0f;
  t.snr = 30.0f;
  t.approaching = (t.speed_kmh > 0.0f);
  t.ttc_s = t.approaching ? (t.range_m / (t.speed_kmh / 3.6f)) : -1.0f;

  d = ew_decide(&t);
  printf("[ew] fake range=%.1fm speed=%.1f approaching=%d -> %s\n",
         t.range_m, t.speed_kmh, (int)t.approaching, d.reason);
  return ew_agent_emit_decision(&d, EW_EVENT_SOURCE_FAKE);
}

/* NSH 可能把带空格 SSID 拆成多个 argv，合并 [from..to] 后再 parse_cli_token */
static void join_argv_tokens(int argc, char **argv, int from, int to,
                             char *out, unsigned out_sz)
{
  int i;
  unsigned n = 0;

  if (out_sz == 0) {
    return;
  }
  out[0] = '\0';
  if (from > to || from >= argc) {
    return;
  }
  if (to >= argc) {
    to = argc - 1;
  }
  for (i = from; i <= to; i++) {
    const char *s = argv[i];
    size_t len;

    if (s == NULL) {
      continue;
    }
    len = strlen(s);
    if (i > from && n + 1 < out_sz) {
      out[n++] = ' ';
    }
    if (n + len + 1 > out_sz) {
      len = out_sz - n - 1;
    }
    memcpy(out + n, s, len);
    n += len;
    out[n] = '\0';
  }
}

static void parse_cli_token(const char *arg, char *out, unsigned out_sz)
{
  const char *p = arg;
  unsigned n = 0;

  if (out_sz == 0) {
    return;
  }
  out[0] = '\0';
  if (arg == NULL) {
    return;
  }
  while (*p != '\0' && (*p == ' ' || *p == '\t')) {
    p++;
  }
  if (*p == '"') {
    p++;
    while (*p != '\0' && *p != '"' && n + 1 < out_sz) {
      out[n++] = *p++;
    }
    if (*p == '"') {
      p++;
    }
  } else {
    while (*p != '\0' && *p != ' ' && *p != '\t' && n + 1 < out_sz) {
      out[n++] = *p++;
    }
  }
  out[n] = '\0';
}

static int cmd_wifi(int argc, char **argv)
{
  static const char *state_name[] = {
    "modem not responding", "not connected", "connected (LAN only)", "online"
  };
  char status[EW_WIFI_STAT_MAX];
  const char *sub = (argc >= 3) ? argv[2] : "";

  if (strcmp(sub, "scan") == 0) {
    ew_wifi_ap_t aps[EW_WIFI_SCAN_MAX];
    int n = ew_wifi_scan(aps, EW_WIFI_SCAN_MAX);
    int i;

    if (n < 0) {
      printf("[ew-wifi] scan failed\n");
      return 1;
    }
    for (i = 0; i < n; i++) {
      printf("  %-32s %4d dBm  %s\n", aps[i].ssid, aps[i].rssi,
             aps[i].open ? "open" : "locked");
    }
    printf("[ew-wifi] %d network(s)\n", n);
    return 0;
  }

  if (strcmp(sub, "join") == 0) {
    char ssid[EW_WIFI_SSID_MAX];
    char pass[EW_WIFI_PASS_MAX];
    char raw[EW_WIFI_SSID_MAX * 2];
    int rc;

    if (argc < 4) {
      printf("usage: ew wifi join <ssid> [password]\n");
      printf("  ssid with spaces: ew wifi join \"Pura 80 Pro+\" pass\n");
      return 1;
    }
    if (argc >= 5) {
      join_argv_tokens(argc, argv, 3, argc - 2, raw, sizeof(raw));
      parse_cli_token(raw, ssid, sizeof(ssid));
      parse_cli_token(argv[argc - 1], pass, sizeof(pass));
    } else {
      parse_cli_token(argv[3], ssid, sizeof(ssid));
      pass[0] = '\0';
    }
    rc = ew_wifi_join(ssid, pass, status, sizeof(status));
    printf("[ew-wifi] %s\n", status);
    return rc;
  }

  if (strcmp(sub, "probe") == 0) {
    ew_wifi_ap_t ap;
    char raw[EW_WIFI_SSID_MAX * 2];

    if (argc < 4) {
      printf("usage: ew wifi probe <ssid>\n");
      printf("  ew wifi probe \"Pura 80 Pro+\"\n");
      return 1;
    }
    join_argv_tokens(argc, argv, 3, argc - 1, raw, sizeof(raw));
    parse_cli_token(raw, status, sizeof(status));
    if (ew_wifi_probe_ssid(status, &ap) != 0) {
      printf("[ew-wifi] probe miss: %s\n", status);
      return 1;
    }
    printf("[ew-wifi] probe hit: %s  %d dBm  %s\n", ap.ssid, ap.rssi,
           ap.open ? "open" : "locked");
    return 0;
  }

  if (strcmp(sub, "forget") == 0) {
    return ew_wifi_forget();
  }

  if (strcmp(sub, "ping") == 0) {
    return ew_wifi_at_diag();
  }

  if (strcmp(sub, "raw") == 0) {
    return ew_wifi_at_status();
  }

  {
    char ip[24];
    ew_wifi_state_t st = ew_wifi_probe(1, ip, sizeof(ip));

    printf("[ew-wifi] %s%s%s\n", state_name[st], ip[0] ? "  ip=" : "", ip);
    if (ew_wifi_cred_load(status, sizeof(status), NULL, 0) == 0) {
      printf("[ew-wifi] saved ssid: %s\n", status);
    }
    return (st == EW_WIFI_DOWN) ? 1 : 0;
  }
}

static int cmd_ask(int argc, char **argv)
{
  char reply[512];
  const char *q = (argc >= 3) ? argv[2] : "你好";

  if (ew_llm_ask(q, reply, sizeof(reply)) != 0) {
    printf("[ew-ask] fail: %s\n", reply);
    return 1;
  }
  printf("[ew-ask] %s\n", reply);
  return 0;
}

static int cmd_loop(void)
{
#ifdef __NuttX__
  ew_alert_level_t last = (ew_alert_level_t)-1;
  ew_link_t last_link = (ew_link_t)-1;
  int ret = ew_safety_start();
  if (ret != 0) {
    printf("[ew-safety] start failed result=%d\n", ret);
    return 1;
  }
  printf("[ew] observing independent radar safety task on %s\n", EW_RADAR_DEV);
  for (;;) {
    ew_safety_snapshot_t safety;
    ew_safety_snapshot(&safety);
    if (safety.decision.level != last || safety.decision.link != last_link) {
      printf("[ew] safety %s range=%.1fm %s link=%d frames=%lu error=%d\n",
             ew_alert_level_name(safety.decision.level), safety.decision.range_m,
             safety.decision.reason, (int)safety.decision.link,
             (unsigned long)safety.sniff.frames_ok, safety.radar_error);
      last = safety.decision.level;
      last_link = safety.decision.link;
    }
    usleep(20000);
  }
#else
  printf("[ew] host stub: try `ew fake 10 20` or `ew alert soft`\n");
#endif
  return 0;
}

static int cmd_help(void)
{
  printf("usage:\n");
  printf("  ew                          read radar on %s\n", EW_RADAR_DEV);
  printf("  ew boot                     LVGL UI loop (used by rcS)\n");
  printf("  ew chat                     jump straight to the agent page\n");
  printf("  ew alert none|soft|strong|crit [reason]\n");
  printf("  ew fake [range_m] [speed]   feed a synthetic target\n");
  printf("  ew buzz [freq_hz] [ms]      PA28 passive buzzer\n");
  printf("  ew screen [info]            LCD colour selftest / resolution\n");
  printf("  ew wifi                     link state + saved ssid\n");
  printf("  ew wifi scan                list nearby networks\n");
  printf("  ew wifi join <ssid> [pass]  connect and remember\n");
  printf("  ew wifi probe <ssid>        directed scan one SSID\n");
  printf("  ew wifi forget              drop saved credentials\n");
  printf("  ew wifi ping                MODEM/WiFi/LAN/ONLINE layered check\n");
  printf("  ew wifi raw                 AT+GMR/CWMODE?/CWJAP?/CIPSTA?\n");
  printf("  ew at <cmd>                 raw AT, e.g. ew at AT+CIFSR\n");
  printf("  ew ask <text>               one-shot LLM question\n");
  return 0;
}

int main(int argc, char *argv[])
{
  const char *cmd = (argc >= 2) ? argv[1] : "";

  if (strcmp(cmd, "alert") == 0) {
    return cmd_alert(argc, argv);
  }
  if (strcmp(cmd, "fake") == 0) {
    return cmd_fake(argc, argv);
  }
  if (strcmp(cmd, "screen") == 0) {
    return cmd_screen(argc, argv);
  }
  if (strcmp(cmd, "buzz") == 0 || strcmp(cmd, "buzzer") == 0) {
    return cmd_buzz(argc, argv);
  }
  if (strcmp(cmd, "wifi") == 0) {
    return cmd_wifi(argc, argv);
  }
  if (strcmp(cmd, "at") == 0) {
    return ew_wifi_at_cmd((argc >= 3) ? argv[2] : "AT");
  }
  if (strcmp(cmd, "boot") == 0) {
    alert_lcd_boot_splash();
    printf("[ew-boot] UI loop returned (unexpected)\n");
    fflush(stdout);
    return 0;
  }
  if (strcmp(cmd, "chat") == 0) {
    ew_chat_run();
    return 0;
  }
  if (strcmp(cmd, "ask") == 0) {
    return cmd_ask(argc, argv);
  }
  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "-h") == 0) {
    return cmd_help();
  }

  printf("edge_walker · radar %s\n", EW_RADAR_DEV);
  return cmd_loop();
}
