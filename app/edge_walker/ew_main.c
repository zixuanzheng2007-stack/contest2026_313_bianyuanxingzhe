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
    } else {
      level = EW_ALERT_SOFT;
    }
  }
  if (argc >= 4) {
    reason = argv[3];
  }

  alert_output(level, reason);
  return 0;
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
  alert_output(d.level, d.reason);
  return 0;
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
    int rc;

    if (argc < 4) {
      printf("usage: ew wifi join <ssid> [password]\n");
      return 1;
    }
    rc = ew_wifi_join(argv[3], (argc >= 5) ? argv[4] : "", status,
                      sizeof(status));
    printf("[ew-wifi] %s\n", status);
    return rc;
  }

  if (strcmp(sub, "forget") == 0) {
    return ew_wifi_forget();
  }

  if (strcmp(sub, "ping") == 0) {
    return ew_wifi_at_ping();
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
  uint8_t buf[64];
  ew_track_t track;
  ew_hold_t hold;
  ew_sniff_stats_t sniff;
  ew_alert_level_t last = EW_ALERT_NONE;
  int fd = open(EW_RADAR_DEV, O_RDONLY);

  if (fd < 0) {
    printf("[ew] open %s failed\n", EW_RADAR_DEV);
    return 1;
  }

  ew_hold_reset(&hold);
  memset(&sniff, 0, sizeof(sniff));
  printf("[ew] reading %s, Ctrl-C to stop\n", EW_RADAR_DEV);

  for (;;) {
    ew_sniff_stats_t before = sniff;
    const ew_track_t *tp = NULL;
    bool had_bytes = false;
    bool had_frame = false;
    ew_decision_t d;
    struct timespec ts;
    uint32_t now = 0;
    int n = read(fd, buf, sizeof(buf));

    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
      now = (uint32_t)((uint64_t)ts.tv_sec * 1000u +
                       (uint64_t)ts.tv_nsec / 1000000u);
    }

    if (n > 0) {
      had_bytes = true;
      memset(&track, 0, sizeof(track));
      if (ew_ld2451_feed_sniff(buf, (unsigned)n, &sniff, &track) &&
          track.valid) {
        tp = &track;
      }
      had_frame = (sniff.frames_ok > before.frames_ok);
    } else {
      usleep(20000);
    }

    d = ew_hold_update(&hold, now, had_bytes, had_frame, tp);
    if (d.level != last) {
      printf("[ew] latch %s range=%.1fm %s link=%d\n",
             ew_alert_level_name(d.level), d.range_m, d.reason, (int)d.link);
      ew_agent_proactive_alert(d.level, d.range_m, d.reason);
      last = d.level;
    }
  }
#else
  printf("[ew] host stub: try `ew fake 10 2` or `ew alert soft`\n");
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
  printf("  ew wifi forget              drop saved credentials\n");
  printf("  ew wifi ping|raw            AT handshake / CWJAP?+CIFSR\n");
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
