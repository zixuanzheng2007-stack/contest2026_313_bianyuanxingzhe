/****************************************************************************
 * LD2451 流式解析 + 端侧 policy（F · 王筠昊）
 *
 * 职责：把 UART 字节流还原成目标，再按距离/TTC 判告警等级。
 * 不调用 LLM；不直接驱马达（出口走 alert_output）。
 *
 * 上报帧（HLK 串口协议 V1.03）：
 *   [F4 F3 F2 F1][len_le 2B][body][F8 F7 F6 F5]
 * body:
 *   count(1) + alarm(1) + N * { angle, range_m, dir, speed_kmh, snr }  // 各 1B
 *
 * 选型策略：在靠近且速度≥初值的目标里，取最近一个进入 policy。
 ****************************************************************************/

#include "ew_ld2451.h"

#include <string.h>

enum {
  ST_HDR0 = 0,
  ST_HDR1,
  ST_HDR2,
  ST_HDR3,
  ST_LEN0,
  ST_LEN1,
  ST_BODY,
  ST_TAIL0,
  ST_TAIL1,
  ST_TAIL2,
  ST_TAIL3
};

#define EW_MAX_BODY 64

static int g_st = ST_HDR0;
static uint8_t g_body[EW_MAX_BODY];
static unsigned g_body_len;
static unsigned g_expect_body;
static uint8_t g_len_lo;

void ew_ld2451_reset(void)
{
  g_st = ST_HDR0;
  g_body_len = 0;
  g_expect_body = 0;
  g_len_lo = 0;
}

const char *ew_alert_level_name(ew_alert_level_t level)
{
  switch (level) {
    case EW_ALERT_SOFT:
      return "SOFT";
    case EW_ALERT_STRONG:
      return "STRONG";
    case EW_ALERT_EMERGENCY:
      return "EMERGENCY";
    case EW_ALERT_NONE:
    default:
      return "NONE";
  }
}

/* 解析一帧 body，选出最近的有效靠近目标写入 out。 */
static bool decode_body(const uint8_t *body, unsigned len, ew_track_t *out)
{
  unsigned count;
  unsigned i;
  bool have = false;
  ew_track_t best;

  memset(out, 0, sizeof(*out));
  out->ttc_s = -1.0f;
  memset(&best, 0, sizeof(best));
  best.ttc_s = -1.0f;

  if (body == NULL || len < 2) {
    return false;
  }

  count = body[0];
  /* body[1]=alarm（帧级有无靠近）；是否告警仍以每目标 dir 为准 */
  (void)body[1];

  if (count > EW_LD2451_MAX_TARGETS) {
    count = EW_LD2451_MAX_TARGETS;
  }

  if (len < 2u + count * 5u) {
    return false;
  }

  for (i = 0; i < count; i++) {
    const uint8_t *t = &body[2 + i * 5];
    float range_m = (float)t[1];
    uint8_t dir = t[2];
    float speed_kmh = (float)t[3];
    bool approaching = (dir == (uint8_t)EW_DIR_APPROACH);
    float ttc = -1.0f;

    if (!approaching) {
      continue;
    }
    if (speed_kmh < EW_MIN_SPEED_KMH) {
      continue;
    }

    /* TTC 仅端侧：distance_m / (speed_kmh / 3.6)，方向必须为靠近 */
    if (speed_kmh > 0.0f) {
      ttc = range_m / (speed_kmh / 3.6f);
    }

    if (!have || range_m < best.range_m) {
      best.valid = true;
      best.approaching = true;
      best.range_m = range_m;
      best.speed_kmh = speed_kmh;
      best.azimuth_deg = (float)((int)t[0] - 0x80); /* 协议：上报值 - 0x80 */
      best.snr = (float)t[4];
      best.ttc_s = ttc;
      have = true;
    }
  }

  if (!have) {
    return false;
  }

  *out = best;
  return true;
}

bool ew_ld2451_feed(const uint8_t *data, unsigned len, ew_track_t *out)
{
  bool got = false;

  if (data == NULL || out == NULL) {
    return false;
  }

  for (unsigned i = 0; i < len; i++) {
    uint8_t b = data[i];

    switch (g_st) {
      case ST_HDR0:
        g_st = (b == EW_LD2451_HDR0) ? ST_HDR1 : ST_HDR0;
        break;
      case ST_HDR1:
        g_st = (b == EW_LD2451_HDR1) ? ST_HDR2 : ST_HDR0;
        break;
      case ST_HDR2:
        g_st = (b == EW_LD2451_HDR2) ? ST_HDR3 : ST_HDR0;
        break;
      case ST_HDR3:
        g_st = (b == EW_LD2451_HDR3) ? ST_LEN0 : ST_HDR0;
        break;
      case ST_LEN0:
        g_len_lo = b;
        g_st = ST_LEN1;
        break;
      case ST_LEN1:
        /* 小端长度：低字节在前 */
        g_expect_body = (unsigned)g_len_lo | ((unsigned)b << 8);
        g_body_len = 0;
        if (g_expect_body > EW_MAX_BODY) {
          g_st = ST_HDR0; /* 异常长度，重新猎头 */
        } else if (g_expect_body == 0) {
          g_st = ST_TAIL0;
        } else {
          g_st = ST_BODY;
        }
        break;
      case ST_BODY:
        g_body[g_body_len++] = b;
        if (g_body_len >= g_expect_body) {
          g_st = ST_TAIL0;
        }
        break;
      case ST_TAIL0:
        g_st = (b == EW_LD2451_TAIL0) ? ST_TAIL1 : ST_HDR0;
        break;
      case ST_TAIL1:
        g_st = (b == EW_LD2451_TAIL1) ? ST_TAIL2 : ST_HDR0;
        break;
      case ST_TAIL2:
        g_st = (b == EW_LD2451_TAIL2) ? ST_TAIL3 : ST_HDR0;
        break;
      case ST_TAIL3:
        if (b == EW_LD2451_TAIL3) {
          if (decode_body(g_body, g_body_len, out)) {
            got = true; /* 本包内后到的有效帧会覆盖 out */
          }
        }
        g_st = ST_HDR0;
        break;
      default:
        g_st = ST_HDR0;
        break;
    }
  }

  return got;
}

/* 距离门限与 TTC 门限取更严者（先到的高等级优先）。 */
static ew_alert_level_t level_from_range_ttc(float range_m, float ttc_s)
{
  bool ttc_ok = (ttc_s >= 0.0f);

  if (range_m <= EW_RANGE_EMERGENCY_M ||
      (ttc_ok && ttc_s < EW_TTC_EMERGENCY_S)) {
    return EW_ALERT_EMERGENCY;
  }
  if (range_m <= EW_RANGE_STRONG_M ||
      (ttc_ok && ttc_s < EW_TTC_STRONG_S)) {
    return EW_ALERT_STRONG;
  }
  if (range_m <= EW_RANGE_SOFT_M ||
      (ttc_ok && ttc_s <= EW_TTC_SOFT_S)) {
    return EW_ALERT_SOFT;
  }
  return EW_ALERT_NONE;
}

ew_decision_t ew_decide(const ew_track_t *track)
{
  ew_decision_t d;

  memset(&d, 0, sizeof(d));
  d.level = EW_ALERT_NONE;
  d.ttc_s = -1.0f;
  d.reason = "idle";

  if (track == NULL || !track->valid) {
    d.reason = "invalid_track";
    return d;
  }

  d.range_m = track->range_m;
  d.speed_kmh = track->speed_kmh;
  d.azimuth_deg = track->azimuth_deg;
  d.ttc_s = track->ttc_s;
  d.approaching = track->approaching;

  if (!track->approaching) {
    d.reason = "not_approaching";
    return d;
  }
  if (track->speed_kmh < EW_MIN_SPEED_KMH) {
    d.reason = "below_min_speed";
    return d;
  }

  d.level = level_from_range_ttc(track->range_m, track->ttc_s);
  if (d.level == EW_ALERT_NONE) {
    d.reason = "out_of_threshold";
  } else if (d.level == EW_ALERT_EMERGENCY) {
    d.reason = "emergency_range_or_ttc";
  } else if (d.level == EW_ALERT_STRONG) {
    d.reason = "strong_range_or_ttc";
  } else {
    d.reason = "soft_range_or_ttc";
  }

  return d;
}
