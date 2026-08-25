/****************************************************************************
 * 主机冒烟：不依赖 NuttX，验证 LD2451 解析 + policy
 *
 *   gcc -O2 -Wall -o host_smoke host_smoke.c ew_ld2451.c && ./host_smoke
 *
 * 覆盖：官方示例帧、SOFT/STRONG/EMERGENCY 夹具、远离与低速过滤。
 * 期望末行：ALL PASS
 ****************************************************************************/

#include "ew_ld2451.h"

#include <stdio.h>
#include <string.h>

static const uint8_t k_official[] = {
  0xF4, 0xF3, 0xF2, 0xF1,
  0x11, 0x00,
  0x03, 0x01,
  0x8A, 0x28, 0x00, 0x3C, 0x15,
  0x8A, 0x1E, 0x01, 0x3C, 0x0F,
  0x76, 0x5F, 0x00, 0x3C, 0x0F,
  0xF8, 0xF7, 0xF6, 0xF5
};

static void frame_one(uint8_t *out, unsigned *len,
                      uint8_t range_m, uint8_t dir, uint8_t speed)
{
  out[0] = 0xF4; out[1] = 0xF3; out[2] = 0xF2; out[3] = 0xF1;
  out[4] = 0x07; out[5] = 0x00;
  out[6] = 0x01;
  out[7] = (dir == (uint8_t)EW_DIR_APPROACH) ? 0x01 : 0x00;
  out[8] = 0x80;
  out[9] = range_m;
  out[10] = dir;
  out[11] = speed;
  out[12] = 30;
  out[13] = 0xF8; out[14] = 0xF7; out[15] = 0xF6; out[16] = 0xF5;
  *len = 17;
}

static int expect_level(const char *tag, const uint8_t *frame, unsigned len,
                        ew_alert_level_t want, int expect_track)
{
  ew_track_t t;
  ew_decision_t d;
  bool got;

  ew_ld2451_reset();
  memset(&t, 0, sizeof(t));
  got = ew_ld2451_feed(frame, len, &t);

  if (expect_track) {
    if (!got || !t.valid) {
      printf("FAIL %s: expected track\n", tag);
      return 1;
    }
    d = ew_decide(&t);
    printf("  %s: range=%.1f speed=%.1f az=%.0f ttc=%.2f -> %s\n",
           tag, t.range_m, t.speed_kmh, t.azimuth_deg, t.ttc_s,
           ew_alert_level_name(d.level));
    if (d.level != want) {
      printf("FAIL %s: want %s got %s\n", tag,
             ew_alert_level_name(want), ew_alert_level_name(d.level));
      return 1;
    }
  } else {
    if (got && t.valid) {
      printf("FAIL %s: expected no track\n", tag);
      return 1;
    }
    printf("  %s: no valid approaching target (ok)\n", tag);
  }
  return 0;
}

int main(void)
{
  uint8_t f[32];
  unsigned n;
  int fail = 0;

  printf("edge_walker host_smoke\n");

  /* 官方示例：最近靠近目标 40m @60km/h → SOFT（距离>25 但 TTC=2.4s <3 → STRONG）
   * TTC = 40 / (60/3.6) = 40/16.667 ≈ 2.4s → STRONG by TTC */
  fail += expect_level("official", k_official, sizeof(k_official),
                       EW_ALERT_STRONG, 1);

  frame_one(f, &n, 22, (uint8_t)EW_DIR_APPROACH, 20);
  /* TTC=22/(20/3.6)=3.96s，距离 22≤25 → SOFT */
  fail += expect_level("soft", f, n, EW_ALERT_SOFT, 1);

  frame_one(f, &n, 12, (uint8_t)EW_DIR_APPROACH, 25);
  fail += expect_level("strong", f, n, EW_ALERT_STRONG, 1);

  frame_one(f, &n, 6, (uint8_t)EW_DIR_APPROACH, 40);
  fail += expect_level("emergency", f, n, EW_ALERT_EMERGENCY, 1);

  frame_one(f, &n, 12, (uint8_t)EW_DIR_AWAY, 40);
  fail += expect_level("away", f, n, EW_ALERT_NONE, 0);

  frame_one(f, &n, 10, (uint8_t)EW_DIR_APPROACH, 3);
  fail += expect_level("slow", f, n, EW_ALERT_NONE, 0);

  if (fail == 0) {
    printf("ALL PASS\n");
    return 0;
  }
  printf("%d FAIL\n", fail);
  return 1;
}
