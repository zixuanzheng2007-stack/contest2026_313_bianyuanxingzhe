/****************************************************************************
 * 边缘行者主程序（NSH 命令 `ew`）
 *
 * 分工：
 *   F：parse / fixture / fake 走 LD2451 解析 + policy
 *   H：alert_output / LCD；真机 UART 读环
 *
 * 无雷达时可测：
 *   ew parse | ew fixture soft|strong|emergency|away | ew fake 20 30
 * 有雷达后：
 *   ew                 # 读 /dev/ttyS1 @115200
 *
 * 控制台口是主机 USB 1Mbps（RTS 须拉低）；雷达口是板上 UART2。
 ****************************************************************************/

#include "alert_lcd.h"
#include "alert_output.h"
#include "ew_ld2451.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __NuttX__
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#endif

#ifndef EW_RADAR_DEV
#define EW_RADAR_DEV "/dev/ttyS1"
#endif

/* HLK V1.03 文档示例帧（3 目标；含靠近与远离） */
static const uint8_t k_official_example[] = {
  0xF4, 0xF3, 0xF2, 0xF1,
  0x11, 0x00,
  0x03, 0x01,
  0x8A, 0x28, 0x00, 0x3C, 0x15, /* 10°, 40m, approach, 60km/h */
  0x8A, 0x1E, 0x01, 0x3C, 0x0F, /* 10°, 30m, away, 60km/h */
  0x76, 0x5F, 0x00, 0x3C, 0x0F, /* -10°, 95m, approach, 60km/h */
  0xF8, 0xF7, 0xF6, 0xF5
};

static void build_single_target_frame(uint8_t *out, unsigned *out_len,
                                      uint8_t angle_raw, uint8_t range_m,
                                      uint8_t dir, uint8_t speed_kmh,
                                      uint8_t snr)
{
  /* 头 + 长度 7 + 体(count/alarm/5B) + 尾 */
  out[0] = 0xF4;
  out[1] = 0xF3;
  out[2] = 0xF2;
  out[3] = 0xF1;
  out[4] = 0x07;
  out[5] = 0x00;
  out[6] = 0x01;
  out[7] = (dir == (uint8_t)EW_DIR_APPROACH) ? 0x01 : 0x00;
  out[8] = angle_raw;
  out[9] = range_m;
  out[10] = dir;
  out[11] = speed_kmh;
  out[12] = snr;
  out[13] = 0xF8;
  out[14] = 0xF7;
  out[15] = 0xF6;
  out[16] = 0xF5;
  *out_len = 17;
}

static void print_decision(const ew_track_t *t, const ew_decision_t *d)
{
  printf("[ew] track range=%.1fm speed=%.1fkm/h az=%.0f° ttc=%.2fs "
         "approaching=%d -> %s (%s)\n",
         t->range_m, t->speed_kmh, t->azimuth_deg, t->ttc_s,
         (int)t->approaching,
         ew_alert_level_name(d->level), d->reason);
}

static int feed_and_decide(const uint8_t *frame, unsigned len)
{
  ew_track_t track;
  ew_decision_t d;
  bool got;

  ew_ld2451_reset();
  memset(&track, 0, sizeof(track));
  got = ew_ld2451_feed(frame, len, &track);
  if (!got || !track.valid) {
    printf("[ew] parse: no valid approaching target\n");
    alert_output(EW_ALERT_NONE, "no_valid_target");
    return 1;
  }

  d = ew_decide(&track);
  print_decision(&track, &d);
  alert_output(d.level, d.reason);
  return 0;
}

static int cmd_alert(int argc, char **argv)
{
  ew_alert_level_t level = EW_ALERT_SOFT;
  const char *reason = "manual_test";

  if (argc >= 3) {
    if (strcmp(argv[2], "none") == 0 || strcmp(argv[2], "0") == 0) {
      level = EW_ALERT_NONE;
    } else if (strcmp(argv[2], "soft") == 0 || strcmp(argv[2], "warn") == 0 ||
               strcmp(argv[2], "1") == 0) {
      level = EW_ALERT_SOFT;
    } else if (strcmp(argv[2], "strong") == 0 || strcmp(argv[2], "2") == 0) {
      level = EW_ALERT_STRONG;
    } else if (strcmp(argv[2], "emergency") == 0 ||
               strcmp(argv[2], "crit") == 0 || strcmp(argv[2], "3") == 0) {
      level = EW_ALERT_EMERGENCY;
    } else {
      printf("[ew] unknown level '%s'\n", argv[2]);
      return 1;
    }
  }
  if (argc >= 4) {
    reason = argv[3];
  }

  alert_output(level, reason);
  return 0;
}

static int cmd_fake(int argc, char **argv)
{
  ew_track_t t;
  ew_decision_t d;

  memset(&t, 0, sizeof(t));
  t.valid = true;
  t.range_m = (argc >= 3) ? (float)atof(argv[2]) : 20.0f;
  t.speed_kmh = (argc >= 4) ? (float)atof(argv[3]) : 30.0f;
  t.azimuth_deg = 0.0f;
  t.approaching = (t.speed_kmh > 0.0f);
  if (t.approaching && t.speed_kmh > 0.0f) {
    t.ttc_s = t.range_m / (t.speed_kmh / 3.6f);
  } else {
    t.ttc_s = -1.0f;
    t.approaching = false;
  }

  d = ew_decide(&t);
  print_decision(&t, &d);
  alert_output(d.level, d.reason);
  return 0;
}

static int cmd_parse(void)
{
  printf("[ew] parse official V1.03 example frame\n");
  return feed_and_decide(k_official_example, sizeof(k_official_example));
}

static int cmd_fixture(int argc, char **argv)
{
  uint8_t frame[32];
  unsigned len = 0;
  const char *name = (argc >= 3) ? argv[2] : "strong";

  if (strcmp(name, "empty") == 0) {
    frame[0] = 0xF4;
    frame[1] = 0xF3;
    frame[2] = 0xF2;
    frame[3] = 0xF1;
    frame[4] = 0x02;
    frame[5] = 0x00;
    frame[6] = 0x00;
    frame[7] = 0x00;
    frame[8] = 0xF8;
    frame[9] = 0xF7;
    frame[10] = 0xF6;
    frame[11] = 0xF5;
    len = 12;
  } else if (strcmp(name, "away") == 0) {
    build_single_target_frame(frame, &len, 0x80, 12, (uint8_t)EW_DIR_AWAY, 40, 20);
  } else if (strcmp(name, "soft") == 0) {
    /* 22 m @ 20 km/h → SOFT by range */
    build_single_target_frame(frame, &len, 0x80, 22, (uint8_t)EW_DIR_APPROACH, 20, 30);
  } else if (strcmp(name, "emergency") == 0) {
    build_single_target_frame(frame, &len, 0x80, 6, (uint8_t)EW_DIR_APPROACH, 40, 40);
  } else {
    /* strong: 12 m @ 25 km/h */
    build_single_target_frame(frame, &len, 0x80, 12, (uint8_t)EW_DIR_APPROACH, 25, 35);
    name = "strong";
  }

  printf("[ew] fixture '%s' (%u bytes)\n", name, len);
  return feed_and_decide(frame, len);
}

static int cmd_loop(void)
{
#ifdef __NuttX__
  uint8_t buf[64];
  ew_track_t track;
  int fd = open(EW_RADAR_DEV, O_RDONLY | O_NONBLOCK);
  if (fd < 0) {
    printf("[ew] open %s failed\n", EW_RADAR_DEV);
    return 1;
  }

  {
    struct termios tio;
    if (tcgetattr(fd, &tio) == 0) {
      cfsetispeed(&tio, B115200);
      cfsetospeed(&tio, B115200);
      tio.c_cflag = CS8 | CLOCAL | CREAD;
      tio.c_iflag = 0;
      tio.c_oflag = 0;
      tio.c_lflag = 0;
      tcsetattr(fd, TCSANOW, &tio);
    }
  }

  ew_ld2451_reset();
  printf("[ew] reading %s @115200, Ctrl-C to stop\n", EW_RADAR_DEV);
  for (;;) {
    int n = read(fd, buf, sizeof(buf));
    if (n <= 0) {
      usleep(20000);
      continue;
    }
    if (ew_ld2451_feed(buf, (unsigned)n, &track) && track.valid) {
      ew_decision_t d = ew_decide(&track);
      print_decision(&track, &d);
      alert_output(d.level, d.reason);
    }
  }
#else
  printf("[ew] host stub: try `ew parse` / `ew fixture soft` / `ew fake 20 30`\n");
#endif
  return 0;
}

static void print_help(void)
{
  printf("usage:\n");
  printf("  ew                         read radar on %s\n", EW_RADAR_DEV);
  printf("  ew alert soft|strong|emergency|none [reason]\n");
  printf("  ew fake [range_m] [speed_kmh]\n");
  printf("  ew parse                    decode official example frame\n");
  printf("  ew fixture soft|strong|emergency|away|empty\n");
  printf("  ew lcd info|selftest|boot\n");
}

static int cmd_lcd(int argc, char **argv)
{
  if (argc < 3) {
    return alert_lcd_info();
  }
  if (strcmp(argv[2], "selftest") == 0) {
    return alert_lcd_selftest();
  }
  if (strcmp(argv[2], "boot") == 0) {
    alert_lcd_boot_splash();
    return 0;
  }
  return alert_lcd_info();
}

int main(int argc, char *argv[])
{
  printf("edge_walker (F parse/policy + H alert)\n");
  printf("  radar dev: %s\n", EW_RADAR_DEV);

  if (argc >= 2 && strcmp(argv[1], "alert") == 0) {
    return cmd_alert(argc, argv);
  }
  if (argc >= 2 && strcmp(argv[1], "fake") == 0) {
    return cmd_fake(argc, argv);
  }
  if (argc >= 2 && strcmp(argv[1], "parse") == 0) {
    return cmd_parse();
  }
  if (argc >= 2 && strcmp(argv[1], "fixture") == 0) {
    return cmd_fixture(argc, argv);
  }
  if (argc >= 2 && strcmp(argv[1], "lcd") == 0) {
    return cmd_lcd(argc, argv);
  }
  if (argc >= 2 && (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "help") == 0)) {
    print_help();
    return 0;
  }

  return cmd_loop();
}
