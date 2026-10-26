/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * LD2451 流式解析 + 端侧 policy（F · 王筠昊）
 *
 * 职责：把 UART 字节流还原成目标，再按距离/TTC 判告警等级。
 * 不调用 LLM；不直接驱蜂鸣（出口走 alert_output / hold）。
 *
 * 上报帧（HLK 串口协议 V1.03）：
 *   [F4 F3 F2 F1][len_le 2B][body][F8 F7 F6 F5]
 * body:
 *   count(1) + alarm(1) + N * { angle, range_m, dir, speed_kmh, snr }  // 各 1B
 *
 * 选型策略：保留最高告警等级，再比较有效 TTC 和距离，不能只取最近者。
 ****************************************************************************/

#include "ew_ld2451.h"

#include <math.h>
#include <string.h>

#if EW_CONFIRM_FRAMES < 1 || EW_CONFIRM_FRAMES > 255
#error EW_CONFIRM_FRAMES must fit the nonzero uint8_t confirmation counter
#endif

static ew_ld2451_parser_t g_parser;
static int g_sensitivity = EW_SENSITIVITY_STANDARD;

int ew_sensitivity_set(ew_sensitivity_t value)
{
  if (value != EW_SENSITIVITY_STANDARD && value != EW_SENSITIVITY_EARLY) {
    return -1;
  }
  __atomic_store_n(&g_sensitivity, (int)value, __ATOMIC_RELAXED);
  return 0;
}

ew_sensitivity_t ew_sensitivity_get(void)
{
  return (ew_sensitivity_t)__atomic_load_n(&g_sensitivity, __ATOMIC_RELAXED);
}

void ew_ld2451_parser_reset(ew_ld2451_parser_t *parser)
{
  if (parser != NULL) {
    memset(parser, 0, sizeof(*parser));
  }
}

void ew_ld2451_reset(void)
{
  ew_ld2451_parser_reset(&g_parser);
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

/* All body fields are bytes in the supported V1.03 report. A count that is
 * too large or does not exactly match its length is corruption, not an empty
 * scene. Unknown alarm/direction bytes must not silently refresh link health. */
static bool body_valid(const uint8_t *body, unsigned len)
{
  unsigned i;
  /* HLK V1.03 section 1.3: default reports with no targets contain only
   * header, zero length and tail. The physical module emits this 10B frame. */
  if (len == 0u) return true;
  if (len < 2u || body[0] > EW_LD2451_MAX_TARGETS || body[1] > 1u ||
      len != 2u + (unsigned)body[0] * 5u) {
    return false;
  }
  for (i = 0; i < body[0]; i++) {
    uint8_t dir = body[2u + i * 5u + 2u];
    if (dir != (uint8_t)EW_DIR_APPROACH && dir != (uint8_t)EW_DIR_AWAY) {
      return false;
    }
  }
  return true;
}

/* Select by the same decision ordering used across successive UART reads. */
static bool decode_body(const uint8_t *body, unsigned len, ew_track_t *out)
{
  unsigned i;
  bool have = false;
  ew_track_t best;
  memset(&best, 0, sizeof(best));
  best.ttc_s = -1.0f;
  if (body == NULL || len == 0u || !body_valid(body, len)) {
    return false;
  }
  for (i = 0; i < body[0]; i++) {
    const uint8_t *t = &body[2 + i * 5];
    ew_track_t candidate;
    memset(&candidate, 0, sizeof(candidate));
    candidate.valid = true;
    candidate.radar_alarm = body[1] == 1u;
    candidate.approaching = t[2] == (uint8_t)EW_DIR_APPROACH;
    candidate.range_m = (float)t[1];
    candidate.speed_kmh = (float)t[3];
    candidate.azimuth_deg = (float)((int)t[0] - 0x80);
    candidate.snr = (float)t[4];
    candidate.ttc_s = candidate.approaching && candidate.speed_kmh > 0.0f ?
        candidate.range_m / (candidate.speed_kmh / 3.6f) : -1.0f;
    if (!candidate.radar_alarm &&
        (!candidate.approaching || candidate.speed_kmh < EW_MIN_SPEED_KMH ||
         candidate.snr < EW_MIN_SNR)) {
      continue;
    }
    if (ew_track_is_more_urgent(&candidate, have ? &best : NULL)) {
      best = candidate;
      have = true;
    }
  }
  if (have) {
    *out = best;
  }
  return have;
}

static void parser_drop(ew_ld2451_parser_t *parser, unsigned count)
{
  parser->used = (uint8_t)(parser->used - count);
  memmove(parser->buffer, parser->buffer + count, parser->used);
  parser->header_seen = false;
}

bool ew_ld2451_parser_feed_sniff(ew_ld2451_parser_t *parser,
                                 const uint8_t *data, unsigned len,
                                 ew_sniff_stats_t *st, ew_track_t *out)
{
  static const uint8_t header[] = {EW_LD2451_HDR0, EW_LD2451_HDR1,
                                  EW_LD2451_HDR2, EW_LD2451_HDR3};
  static const uint8_t tail[] = {EW_LD2451_TAIL0, EW_LD2451_TAIL1,
                                EW_LD2451_TAIL2, EW_LD2451_TAIL3};
  bool got = false;
  ew_track_t chosen;
  unsigned i;
  memset(&chosen, 0, sizeof(chosen));
  chosen.ttc_s = -1.0f;
  if (out != NULL) {
    memset(out, 0, sizeof(*out));
    out->ttc_s = -1.0f;
  }
  if (parser == NULL || (data == NULL && len != 0)) {
    return false;
  }
  if (parser->used >= sizeof(parser->buffer)) {
    ew_ld2451_parser_reset(parser);
  }
  if (st != NULL) {
    st->bytes_in += len;
  }
  for (i = 0; i < len; i++) {
    parser->buffer[parser->used++] = data[i];
    while (parser->used != 0) {
      unsigned prefix = parser->used < sizeof(header) ?
                          parser->used : sizeof(header);
      unsigned body_len, frame_len;
      ew_track_t candidate;
      if (memcmp(parser->buffer, header, prefix) != 0) {
        parser_drop(parser, 1u);
        continue;
      }
      if (parser->used < sizeof(header)) {
        break;
      }
      if (!parser->header_seen) {
        if (st != NULL) st->headers++;
        parser->header_seen = true;
      }
      if (parser->used < 6u) {
        break;
      }
      body_len = (unsigned)parser->buffer[4] |
                   ((unsigned)parser->buffer[5] << 8);
      if (body_len != 0u &&
          (body_len < 2u || body_len > 2u + EW_LD2451_MAX_TARGETS * 5u ||
           (body_len - 2u) % 5u != 0u)) {
        if (st != NULL) st->frames_bad++;
        parser_drop(parser, 1u);
        continue;
      }
      if (body_len != 0u && ((parser->used >= 7u &&
           (parser->buffer[6] > EW_LD2451_MAX_TARGETS ||
            body_len != 2u + (unsigned)parser->buffer[6] * 5u)) ||
          (parser->used >= 8u && parser->buffer[7] > 1u))) {
        if (st != NULL) st->frames_bad++;
        parser_drop(parser, 1u);
        continue;
      }
      frame_len = body_len + 10u;
      if (parser->used < frame_len) {
        break;
      }
      if (!body_valid(parser->buffer + 6u, body_len) ||
          memcmp(parser->buffer + 6u + body_len, tail, sizeof(tail)) != 0) {
        if (st != NULL) st->frames_bad++;
        /* Keep every suffix: a bad length/tail may have swallowed the header
         * of a following good frame, including one split between reads. */
        parser_drop(parser, 1u);
        continue;
      }
      if (st != NULL) {
        st->frames_ok++;
        if (body_len == 0u || parser->buffer[6] == 0) st->frames_empty++;
        else st->frames_targets++;
      }
      if (decode_body(parser->buffer + 6u, body_len, &candidate)) {
        if (st != NULL) st->approaching++;
        if (ew_track_is_more_urgent(&candidate, got ? &chosen : NULL)) {
          chosen = candidate;
        }
        got = true;
      }
      parser_drop(parser, frame_len);
    }
  }

  if (got && out != NULL) {
    *out = chosen;
  }
  return got;
}

bool ew_ld2451_feed_sniff(const uint8_t *data, unsigned len,
                          ew_sniff_stats_t *st, ew_track_t *out)
{
  return ew_ld2451_parser_feed_sniff(&g_parser, data, len, st, out);
}

bool ew_ld2451_feed(const uint8_t *data, unsigned len, ew_track_t *out)
{
  return ew_ld2451_feed_sniff(data, len, NULL, out);
}

/* 距离门限与 TTC 门限取更严者（先到的高等级优先）。 */
static ew_alert_level_t level_from_range_ttc(float range_m, float ttc_s)
{
  bool ttc_ok = (ttc_s >= 0.0f);
  float factor = ew_sensitivity_get() == EW_SENSITIVITY_EARLY ? 1.25f : 1.0f;

  if (range_m <= EW_RANGE_EMERGENCY_M * factor ||
      (ttc_ok && ttc_s < EW_TTC_EMERGENCY_S * factor)) {
    return EW_ALERT_EMERGENCY;
  }
  if (range_m <= EW_RANGE_STRONG_M * factor ||
      (ttc_ok && ttc_s < EW_TTC_STRONG_S * factor)) {
    return EW_ALERT_STRONG;
  }
  if (range_m <= EW_RANGE_SOFT_M * factor ||
      (ttc_ok && ttc_s <= EW_TTC_SOFT_S * factor)) {
    return EW_ALERT_SOFT;
  }
  return EW_ALERT_NONE;
}

static ew_decision_t empty_decision(const char *reason)
{
  ew_decision_t d;
  memset(&d, 0, sizeof(d));
  d.level = EW_ALERT_NONE;
  d.ttc_s = -1.0f;
  d.reason = reason;
  d.link = EW_LINK_OK;
  return d;
}

static bool track_physical_valid(const ew_track_t *track)
{
  /* Bound synthetic callers to the byte fields the actual sensor supplies.
   * In particular a huge finite speed must not forge a near-zero TTC. Zero
   * distance remains a conservative valid near target, not an idle scene. */
  return isfinite(track->range_m) && track->range_m >= 0.0f &&
         track->range_m <= 255.0f && isfinite(track->speed_kmh) &&
         track->speed_kmh >= 0.0f && track->speed_kmh <= 255.0f &&
         isfinite(track->snr) && track->snr >= 0.0f && track->snr <= 255.0f &&
         isfinite(track->azimuth_deg) && track->azimuth_deg >= -128.0f &&
         track->azimuth_deg <= 127.0f;
}

ew_decision_t ew_decide(const ew_track_t *track)
{
  ew_decision_t d = empty_decision("invalid_track");

  if (track == NULL || !track->valid) {
    return d;
  }

  if (!track_physical_valid(track)) {
    /* Preserve the module's independent alarm fallback, but never export
     * NaN/Inf or invented physical values as measured alert metadata. */
    if (track->radar_alarm) {
      d.level = EW_ALERT_SOFT;
      d.approaching = true;
      d.reason = "radar_alarm_invalid_track";
    }
    return d;
  }

  d.range_m = track->range_m;
  d.speed_kmh = track->speed_kmh;
  d.azimuth_deg = track->azimuth_deg;
  /* Caller-supplied TTC is never authoritative, including negative, NaN,
   * infinite or inconsistent values. Only measured closing motion defines it. */
  if (track->approaching && track->speed_kmh > 0.0f) {
    d.ttc_s = track->range_m / (track->speed_kmh / 3.6f);
    if (!isfinite(d.ttc_s)) d.ttc_s = -1.0f;
  }
  d.approaching = track->approaching || track->radar_alarm;

  if (!track->approaching) {
    if (track->radar_alarm) {
      d.level = EW_ALERT_SOFT;
      d.reason = "radar_alarm";
      return d;
    }
    d.reason = "not_approaching";
    return d;
  }
  if (track->speed_kmh < EW_MIN_SPEED_KMH) {
    if (track->radar_alarm) {
      d.level = EW_ALERT_SOFT;
      d.reason = "radar_alarm";
      return d;
    }
    d.reason = "below_min_speed";
    return d;
  }
  if (track->snr < EW_MIN_SNR) {
    if (track->radar_alarm) {
      d.level = EW_ALERT_SOFT;
      d.reason = "radar_alarm";
      return d;
    }
    d.reason = "below_min_snr";
    return d;
  }

  d.level = level_from_range_ttc(d.range_m, d.ttc_s);
  if (d.level == EW_ALERT_NONE) {
    if (track->radar_alarm) {
      d.level = EW_ALERT_SOFT;
      d.reason = "radar_alarm";
    } else {
      d.reason = "out_of_threshold";
    }
  } else if (d.level == EW_ALERT_EMERGENCY) {
    d.reason = "emergency_range_or_ttc";
  } else if (d.level == EW_ALERT_STRONG) {
    d.reason = "strong_range_or_ttc";
  } else {
    d.reason = "soft_range_or_ttc";
  }

  return d;
}

bool ew_track_is_more_urgent(const ew_track_t *candidate,
                              const ew_track_t *current)
{
  ew_decision_t a, b;
  bool a_ttc, b_ttc;
  if (candidate == NULL || !candidate->valid) return false;
  a = ew_decide(candidate);
  if (!track_physical_valid(candidate) && !candidate->radar_alarm) return false;
  if (current == NULL || !current->valid) return true;
  b = ew_decide(current);
  if (!track_physical_valid(current) && !current->radar_alarm) return true;
  if (a.level != b.level) return a.level > b.level;
  a_ttc = a.ttc_s >= 0.0f;
  b_ttc = b.ttc_s >= 0.0f;
  if (a_ttc != b_ttc) return a_ttc;
  if (a_ttc && a.ttc_s != b.ttc_s) return a.ttc_s < b.ttc_s;
  return a.range_m < b.range_m;
}

void ew_hold_reset(ew_hold_t *h)
{
  if (h == NULL) {
    return;
  }
  memset(h, 0, sizeof(*h));
  h->link = EW_LINK_DEAD;
  h->latched_decision = empty_decision("idle");
  h->latest_decision = empty_decision("idle");
}

ew_decision_t ew_hold_update(ew_hold_t *h, uint32_t now_ms,
                             bool had_bytes, bool had_frame,
                             const ew_track_t *track)
{
  ew_decision_t d = empty_decision("idle");
  ew_decision_t instant = empty_decision("idle");
  ew_alert_level_t raw = EW_ALERT_NONE;

  if (h == NULL) {
    d.reason = "invalid_track";
    d.link = EW_LINK_DEAD;
    return d;
  }

  if (had_bytes || had_frame) {
    h->last_byte_ms = now_ms;
    h->ever_bytes = true;
  }
  if (had_frame) {
    if (h->ever_frame &&
        (uint32_t)(now_ms - h->last_frame_ms) > EW_LINK_STALE_MS) {
      h->pending = EW_ALERT_NONE;
      h->pending_hits = 0;
    }
    h->last_frame_ms = now_ms;
    h->ever_frame = true;
  }

  if (h->ever_frame &&
      (uint32_t)(now_ms - h->last_frame_ms) <= EW_LINK_STALE_MS) {
    h->link = EW_LINK_OK;
  } else if (h->ever_bytes &&
             (uint32_t)(now_ms - h->last_byte_ms) <= EW_LINK_STALE_MS) {
    h->link = EW_LINK_NOISE;
  } else {
    h->link = EW_LINK_DEAD;
  }

  /* A repeated pointer is not a new radar observation. Only callers that saw
   * a complete validated frame may advance confirmation or alert lifetime. */
  if (had_frame) {
    if (track != NULL) instant = ew_decide(track);
    h->latest_decision = instant;
    h->have_observation = true;
    raw = instant.level;
    if (raw != EW_ALERT_NONE) {
      if (raw == h->latched ||
          (h->latched != EW_ALERT_NONE && raw > h->latched)) {
        /* Once active, a more urgent observation must not wait to escalate. */
        h->latched = raw;
        h->latched_decision = instant;
        h->last_alert_ms = now_ms;
        h->pending = raw;
        h->pending_hits = (uint8_t)EW_CONFIRM_FRAMES;
      } else {
        if (raw == h->pending) {
          if (h->pending_hits < 255u) h->pending_hits++;
        } else {
          h->pending = raw;
          h->pending_hits = 1;
        }
        if (h->pending_hits >= (uint8_t)EW_CONFIRM_FRAMES &&
            (h->latched == EW_ALERT_NONE ||
             (uint32_t)(now_ms - h->last_alert_ms) >= EW_CLEAR_MS)) {
          h->latched = raw;
          h->latched_decision = instant;
          h->last_alert_ms = now_ms;
        }
      }
    } else {
      h->pending = EW_ALERT_NONE;
      h->pending_hits = 0;
    }
  }
  /* A lower level may already have completed confirmation during the hold
   * window. At expiry use that real observation rather than inventing an
   * empty scene on a no-frame poll. Its lifetime starts at the actual frame,
   * never at this poll, so repeated pointers cannot keep it alive. */
  if (!had_frame && h->latched != EW_ALERT_NONE &&
      h->pending != EW_ALERT_NONE && h->pending < h->latched &&
      h->pending_hits >= (uint8_t)EW_CONFIRM_FRAMES &&
      h->latest_decision.level == h->pending &&
      (uint32_t)(now_ms - h->last_alert_ms) >= EW_CLEAR_MS &&
      (uint32_t)(now_ms - h->last_frame_ms) < EW_CLEAR_MS) {
    h->latched = h->pending;
    h->latched_decision = h->latest_decision;
    h->last_alert_ms = h->last_frame_ms;
  }
  if (h->latched != EW_ALERT_NONE && raw == EW_ALERT_NONE &&
      (uint32_t)(now_ms - h->last_alert_ms) >= EW_CLEAR_MS) {
    h->latched = EW_ALERT_NONE;
    h->latched_decision = empty_decision("alert_timeout");
    h->pending = EW_ALERT_NONE;
    h->pending_hits = 0;
  }
  if (h->latched != EW_ALERT_NONE) {
    d = h->latched_decision;
  } else if (h->have_observation &&
             h->latest_decision.level == EW_ALERT_NONE) {
    d = h->latest_decision;
  } else if (h->have_observation) {
    d = empty_decision(h->pending_hits != 0 ? "confirming" : "alert_timeout");
  }
  d.level = h->latched;
  d.link = h->link;
  if (d.level == EW_ALERT_NONE && d.link != EW_LINK_OK) {
    d = empty_decision(d.link == EW_LINK_NOISE ? "no_frame" : "no_uart");
    d.link = h->link;
  }
  return d;
}
