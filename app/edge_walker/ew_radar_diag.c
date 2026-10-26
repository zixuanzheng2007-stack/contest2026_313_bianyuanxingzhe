/* SPDX-License-Identifier: Apache-2.0 */
#include "ew_radar_diag.h"

#include <errno.h>
#include <stdio.h>

int ew_radar_diag_format(char *out, size_t capacity, const char *request_id,
                        const ew_safety_snapshot_t *snapshot)
{
  static const char hex[] = "0123456789abcdef";
  char sample_hex[sizeof(snapshot->sample) * 2u + 1u];
  const char *link;
  size_t i;
  int result;

  if (out == NULL || capacity == 0) return -EINVAL;
  out[0] = '\0';
  if (request_id == NULL || snapshot == NULL) return -EINVAL;
  for (i = 0; request_id[i] != '\0'; i++) {
    unsigned char c = (unsigned char)request_id[i];
    if (i >= 48u || !((c >= 'a' && c <= 'z') ||
                      (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '_' || c == '-')) {
      return -EINVAL;
    }
  }
  if (i == 0 || snapshot->sample_bytes > sizeof(snapshot->sample)) {
    return -EINVAL;
  }
  switch (snapshot->decision.link) {
    case EW_LINK_DEAD: link = "dead"; break;
    case EW_LINK_NOISE: link = "noise"; break;
    case EW_LINK_OK: link = "ok"; break;
    default: return -EINVAL;
  }
  for (i = 0; i < snapshot->sample_bytes; i++) {
    sample_hex[i * 2u] = hex[snapshot->sample[i] >> 4];
    sample_hex[i * 2u + 1u] = hex[snapshot->sample[i] & 0x0fu];
  }
  sample_hex[snapshot->sample_bytes * 2u] = '\0';
  if (capacity > EW_RADAR_DIAG_MAX_BYTES) capacity = EW_RADAR_DIAG_MAX_BYTES;
  result = snprintf(out, capacity,
      "{\"v\":1,\"id\":\"%s\",\"origin\":\"device\","
      "\"port\":\"/dev/ttyS1\",\"clock\":\"device_monotonic\","
      "\"running\":%s,\"ever_bytes\":%s,\"ever_frame\":%s,"
      "\"started_ms\":%lu,\"updated_ms\":%lu,\"radar_error\":%d,"
      "\"event_id\":%lu,\"link\":\"%s\","
      "\"sniff\":{\"bytes_in\":%lu,\"headers\":%lu,\"frames_ok\":%lu,"
      "\"frames_bad\":%lu,\"frames_empty\":%lu,\"frames_targets\":%lu,"
      "\"approaching\":%lu},\"read_calls\":%lu,\"read_max_gap_ms\":%lu,"
      "\"sample_total\":%lu,\"sample_bytes\":%u,\"sample_hex\":\"%s\"}",
      request_id, snapshot->running ? "true" : "false",
      snapshot->ever_bytes ? "true" : "false",
      snapshot->ever_frame ? "true" : "false",
      (unsigned long)snapshot->started_ms, (unsigned long)snapshot->updated_ms,
      snapshot->radar_error, snapshot->event_id, link,
      (unsigned long)snapshot->sniff.bytes_in,
      (unsigned long)snapshot->sniff.headers,
      (unsigned long)snapshot->sniff.frames_ok,
      (unsigned long)snapshot->sniff.frames_bad,
      (unsigned long)snapshot->sniff.frames_empty,
      (unsigned long)snapshot->sniff.frames_targets,
      (unsigned long)snapshot->sniff.approaching,
      (unsigned long)snapshot->read_calls,
      (unsigned long)snapshot->read_max_gap_ms,
      (unsigned long)snapshot->sample_total,
      snapshot->sample_bytes, sample_hex);
  if (result < 0 || (size_t)result >= capacity) {
    out[0] = '\0';
    return -ENOSPC;
  }
  return result;
}
