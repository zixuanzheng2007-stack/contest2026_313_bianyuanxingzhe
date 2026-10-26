/* SPDX-License-Identifier: Apache-2.0 */
#include "ew_snapshot.h"

#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int ew_snapshot_format(char *out, size_t capacity, const char *request_id,
                       const ew_safety_snapshot_t *snapshot,
                       unsigned long snapshot_seq)
{
  size_t i;
  const char *link;
  const char *level;
  char range[32] = "null";
  char speed[32] = "null";
  int result;

  if (out == NULL || capacity == 0) {
    return -EINVAL;
  }
  out[0] = '\0';
  if (request_id == NULL || snapshot == NULL || snapshot_seq == 0) {
    return -EINVAL;
  }
  for (i = 0; request_id[i] != '\0'; i++) {
    unsigned char c = (unsigned char)request_id[i];
    if (i >= 48 || !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '_' || c == '-')) {
      return -EINVAL;
    }
  }
  if (i == 0) {
    return -EINVAL;
  }
  if (!snapshot->running || snapshot->radar_error != 0) {
    link = "error";
  } else if (!snapshot->ever_frame) {
    /* UART bytes without a validated LD2451 frame matches alert_lcd NO FRAME. */
    link = snapshot->ever_bytes ? "no_frame" : "waiting";
  } else if (snapshot->decision.link == EW_LINK_OK) {
    link = "ok";
  } else {
    link = "stale";
  }
  switch (snapshot->decision.level) {
    case EW_ALERT_NONE: level = "none"; break;
    case EW_ALERT_SOFT: level = "soft"; break;
    case EW_ALERT_STRONG: level = "strong"; break;
    case EW_ALERT_EMERGENCY: level = "emergency"; break;
    default: return -EINVAL;
  }
  /* Held alarms may outlive observations. Keep their level, but never
   * fabricate zero measurements when no fresh target observation exists. */
  if (strcmp(link, "ok") == 0 && isfinite(snapshot->decision.range_m) &&
      snapshot->decision.range_m > 0.0f &&
      snapshot->decision.range_m <= 10000.0f) {
    snprintf(range, sizeof(range), "%.2f", (double)snapshot->decision.range_m);
    if (isfinite(snapshot->decision.speed_kmh) &&
        snapshot->decision.speed_kmh >= 0.0f &&
        snapshot->decision.speed_kmh <= 10000.0f) {
      snprintf(speed, sizeof(speed), "%.2f", (double)snapshot->decision.speed_kmh);
    }
  }
  result = snprintf(out, capacity,
      "{\"v\":1,\"id\":\"%s\",\"origin\":\"device\",\"connected\":true,"
      "\"radar_link\":\"%s\",\"range_m\":%s,\"speed_kmh\":%s,"
      "\"alert_level\":\"%s\",\"profile\":null,\"event_id\":%lu,"
      "\"updated_ms\":%lu,\"clock\":\"device_monotonic\","
      "\"snapshot_seq\":%lu,\"radar_error\":%d}",
      request_id, link, range, speed, level, snapshot->event_id,
      (unsigned long)snapshot->updated_ms, snapshot_seq, snapshot->radar_error);
  if (result < 0 || (size_t)result >= capacity) {
    out[0] = '\0';
    return -ENOSPC;
  }
  return result;
}
