/****************************************************************************
 * 主机冒烟：不依赖 NuttX，验证 LD2451 解析 + policy + hold
 *
 *   gcc -O2 -Wall -o host_smoke host_smoke.c ew_ld2451.c && ./host_smoke
 *
 * 覆盖：官方示例帧、SOFT/STRONG/EMERGENCY 夹具、远离与低速过滤、
 *       低 SNR、连续确认、空场超时、链路死/噪声。
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
                      uint8_t range_m, uint8_t dir, uint8_t speed, uint8_t snr)
{
  out[0] = 0xF4; out[1] = 0xF3; out[2] = 0xF2; out[3] = 0xF1;
  out[4] = 0x07; out[5] = 0x00;
  out[6] = 0x01;
  out[7] = (dir == (uint8_t)EW_DIR_APPROACH) ? 0x01 : 0x00;
  out[8] = 0x80;
  out[9] = range_m;
  out[10] = dir;
  out[11] = speed;
  out[12] = snr;
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
    printf("  %s: range=%.1f speed=%.1f az=%.0f ttc=%.2f snr=%.0f -> %s\n",
           tag, t.range_m, t.speed_kmh, t.azimuth_deg, t.ttc_s, t.snr,
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

static int fail_eq_level(const char *tag, ew_alert_level_t got, ew_alert_level_t want)
{
  if (got != want) {
    printf("FAIL %s: want %s got %s\n", tag,
           ew_alert_level_name(want), ew_alert_level_name(got));
    return 1;
  }
  printf("  %s: %s\n", tag, ew_alert_level_name(got));
  return 0;
}

static int fail_eq_link(const char *tag, ew_link_t got, ew_link_t want)
{
  if (got != want) {
    printf("FAIL %s: link want %d got %d\n", tag, (int)want, (int)got);
    return 1;
  }
  printf("  %s: link=%d\n", tag, (int)got);
  return 0;
}

static ew_track_t make_track(float range_m, float speed_kmh, float snr)
{
  ew_track_t t;
  memset(&t, 0, sizeof(t));
  t.valid = true;
  t.approaching = true;
  t.range_m = range_m;
  t.speed_kmh = speed_kmh;
  t.snr = snr;
  t.ttc_s = range_m / (speed_kmh / 3.6f);
  return t;
}

static int expect_batch_retention(void)
{
  static const uint8_t empty_frame[] = {
    0xF4, 0xF3, 0xF2, 0xF1, 0x02, 0x00,
    0x00, 0x00,
    0xF8, 0xF7, 0xF6, 0xF5
  };
  uint8_t one[32];
  uint8_t batch[64];
  unsigned n;
  ew_track_t t;

  frame_one(one, &n, 12, (uint8_t)EW_DIR_APPROACH, 25, 30);
  memcpy(batch, one, n);
  memcpy(batch + n, empty_frame, sizeof(empty_frame));
  ew_ld2451_reset();
  memset(&t, 0, sizeof(t));
  if (!ew_ld2451_feed(batch, n + sizeof(empty_frame), &t) ||
      !t.valid || t.range_m != 12.0f) {
    printf("FAIL batch_retention: approach lost after empty frame\n");
    return 1;
  }
  printf("  batch_retention: kept %.1fm approach before empty frame\n", t.range_m);
  return 0;
}

int main(void)
{
  uint8_t f[32];
  unsigned n;
  int fail = 0;
  ew_hold_t hold;
  ew_track_t em;
  ew_decision_t d;

  printf("edge_walker host_smoke\n");

  /* 官方示例：最近靠近目标 40m @60km/h → SOFT（距离>25 但 TTC=2.4s <3 → STRONG）
   * TTC = 40 / (60/3.6) = 40/16.667 ≈ 2.4s → STRONG by TTC */
  fail += expect_level("official", k_official, sizeof(k_official),
                       EW_ALERT_STRONG, 1);

  frame_one(f, &n, 22, (uint8_t)EW_DIR_APPROACH, 20, 30);
  /* TTC=22/(20/3.6)=3.96s，距离 22≤25 → SOFT */
  fail += expect_level("soft", f, n, EW_ALERT_SOFT, 1);
  fail += expect_batch_retention();

  frame_one(f, &n, 12, (uint8_t)EW_DIR_APPROACH, 25, 30);
  fail += expect_level("strong", f, n, EW_ALERT_STRONG, 1);

  frame_one(f, &n, 6, (uint8_t)EW_DIR_APPROACH, 40, 30);
  fail += expect_level("emergency", f, n, EW_ALERT_EMERGENCY, 1);

  frame_one(f, &n, 12, (uint8_t)EW_DIR_AWAY, 40, 30);
  fail += expect_level("away", f, n, EW_ALERT_NONE, 0);

  frame_one(f, &n, 10, (uint8_t)EW_DIR_APPROACH, 3, 30);
  fail += expect_level("slow_module_alarm", f, n, EW_ALERT_SOFT, 1);

  frame_one(f, &n, 8, (uint8_t)EW_DIR_APPROACH, 40, 3);
  fail += expect_level("low_snr_module_alarm", f, n, EW_ALERT_SOFT, 1);

  frame_one(f, &n, 30, (uint8_t)EW_DIR_AWAY, 20, 30);
  f[7] = 0x01; /* 协议报警位优先，覆盖方向字段版本歧义。 */
  fail += expect_level("module_alarm_direction_fallback",
                       f, n, EW_ALERT_SOFT, 1);

  ew_hold_reset(&hold);
  d = ew_hold_update(&hold, 0, false, false, NULL);
  fail += fail_eq_level("hold_idle", d.level, EW_ALERT_NONE);
  fail += fail_eq_link("hold_dead", d.link, EW_LINK_DEAD);

  d = ew_hold_update(&hold, 10, true, false, NULL);
  fail += fail_eq_link("hold_noise", d.link, EW_LINK_NOISE);

  em = make_track(6.0f, 40.0f, 30.0f);
  d = ew_hold_update(&hold, 100, true, true, NULL);
  fail += fail_eq_level("hold_frame_empty", d.level, EW_ALERT_NONE);
  fail += fail_eq_link("hold_ok_link", d.link, EW_LINK_OK);

  d = ew_hold_update(&hold, 150, true, true, &em);
  fail += fail_eq_level("hold_confirm", d.level, EW_ALERT_EMERGENCY);

  d = ew_hold_update(&hold, 400, true, true, &em);
  fail += fail_eq_level("hold_stay", d.level, EW_ALERT_EMERGENCY);

  d = ew_hold_update(&hold, 400 + EW_CLEAR_MS - 10, true, true, NULL);
  fail += fail_eq_level("hold_not_cleared", d.level, EW_ALERT_EMERGENCY);

  d = ew_hold_update(&hold, 400 + EW_CLEAR_MS + 20, true, true, NULL);
  fail += fail_eq_level("hold_clear", d.level, EW_ALERT_NONE);

  d = ew_hold_update(&hold, 400 + EW_CLEAR_MS + EW_LINK_STALE_MS + 40,
                     false, false, NULL);
  fail += fail_eq_link("hold_stale", d.link, EW_LINK_DEAD);

  if (fail == 0) {
    printf("ALL PASS\n");
    return 0;
  }
  printf("%d FAIL\n", fail);
  return 1;
}
