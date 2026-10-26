/* SPDX-License-Identifier: Apache-2.0 */
#include "ew_safety.h"
#include "ew_agent.h"
#include "alert_buzzer.h"

#include <errno.h>
#include <string.h>

#if defined(__NuttX__) || defined(EW_SAFETY_HOST_TEST)
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <time.h>
#include <unistd.h>

#ifndef EW_SAFETY_PERIOD_MS
#define EW_SAFETY_PERIOD_MS 20u
#endif
#define EW_SAFETY_READ_BUDGET 4u
#define EW_SAFETY_EVENTS 32u

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static ew_safety_snapshot_t g_snapshot;
static ew_safety_event_t g_events[EW_SAFETY_EVENTS];
static unsigned g_event_head, g_event_count;
static bool g_started;

typedef struct {
  uint8_t sample[64];
  unsigned sample_bytes;
  uint32_t sample_total;
  uint32_t read_calls;
  uint32_t read_max_gap_ms;
} radar_capture_t;

static void capture_bytes(radar_capture_t *capture, const uint8_t *bytes,
                          unsigned size)
{
  unsigned keep;
  capture->sample_total += size;
  if (size >= sizeof(capture->sample)) {
    memcpy(capture->sample, bytes + size - sizeof(capture->sample),
           sizeof(capture->sample));
    capture->sample_bytes = sizeof(capture->sample);
    return;
  }
  keep = capture->sample_bytes;
  if (keep + size > sizeof(capture->sample)) {
    keep = sizeof(capture->sample) - size;
    memmove(capture->sample,
            capture->sample + capture->sample_bytes - keep, keep);
  }
  memcpy(capture->sample + keep, bytes, size);
  capture->sample_bytes = keep + size;
}

static uint32_t monotonic_ms(uint32_t previous)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
    return (uint32_t)((uint64_t)ts.tv_sec * 1000u +
                       (uint64_t)ts.tv_nsec / 1000000u);
  }
  return previous + EW_SAFETY_PERIOD_MS;
}

static void publish_snapshot(const ew_decision_t *d, const ew_hold_t *hold,
                             const ew_sniff_stats_t *sniff, uint32_t now,
                             int radar_error, const radar_capture_t *capture)
{
  pthread_mutex_lock(&g_lock);
  if (d->level != g_snapshot.decision.level ||
      d->link != g_snapshot.decision.link) {
    unsigned slot;
    g_snapshot.event_id = ew_agent_next_event_id();
    if (g_event_count == EW_SAFETY_EVENTS) {
      g_event_head = (g_event_head + 1u) % EW_SAFETY_EVENTS;
      g_event_count--;
      g_snapshot.dropped_events++;
    }
    slot = (g_event_head + g_event_count++) % EW_SAFETY_EVENTS;
    g_events[slot].decision = *d;
    g_events[slot].event_id = g_snapshot.event_id;
  }
  g_snapshot.decision = *d;
  g_snapshot.sniff = *sniff;
  g_snapshot.updated_ms = now;
  g_snapshot.radar_error = radar_error;
  g_snapshot.ever_bytes = hold->ever_bytes;
  g_snapshot.ever_frame = hold->ever_frame;
  memcpy(g_snapshot.sample, capture->sample, capture->sample_bytes);
  g_snapshot.sample_bytes = capture->sample_bytes;
  g_snapshot.sample_total = capture->sample_total;
  g_snapshot.read_calls = capture->read_calls;
  g_snapshot.read_max_gap_ms = capture->read_max_gap_ms;
  pthread_mutex_unlock(&g_lock);
}

static void *safety_worker(void *unused)
{
  ew_ld2451_parser_t parser;
  ew_hold_t hold;
  ew_sniff_stats_t sniff = {0};
  radar_capture_t capture = {0};
  uint32_t now = 0;
  uint32_t last_poll_ms = 0;
  int fd = -1;
  int radar_error = 0;
  (void)unused;
  ew_ld2451_parser_reset(&parser);
  ew_hold_reset(&hold);
  now = monotonic_ms(now);
  pthread_mutex_lock(&g_lock);
  g_snapshot.started_ms = now;
  pthread_mutex_unlock(&g_lock);
  for (;;) {
    bool had_bytes = false;
    ew_decision_t d;
    unsigned read_count;
    now = monotonic_ms(now);
    if (last_poll_ms != 0 && (uint32_t)(now - last_poll_ms) > capture.read_max_gap_ms)
      capture.read_max_gap_ms = (uint32_t)(now - last_poll_ms);
    last_poll_ms = now;
    if (fd < 0) {
      fd = open(EW_RADAR_DEV, O_RDONLY | O_NONBLOCK);
      radar_error = fd < 0 ? errno : 0;
    }
    for (read_count = 0; fd >= 0 && read_count < EW_SAFETY_READ_BUDGET;
         read_count++) {
      uint8_t bytes[64];
      unsigned byte;
      ssize_t n = read(fd, bytes, sizeof(bytes));
      capture.read_calls++;
      if (n <= 0) {
        if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
          radar_error = errno;
          close(fd);
          fd = -1;
          ew_ld2451_parser_reset(&parser);
        }
        break;
      }
      had_bytes = true;
      radar_error = 0;
      capture_bytes(&capture, bytes, (unsigned)n);
      for (byte = 0; byte < (unsigned)n; byte++) {
        ew_track_t candidate;
        uint32_t frames_before = sniff.frames_ok;
        bool have = ew_ld2451_parser_feed_sniff(&parser, bytes + byte, 1,
                                                &sniff, &candidate);
        if (sniff.frames_ok != frames_before) {
          /* Confirmation counts sensor frames, never read() calls or UI ticks. */
          d = ew_hold_update(&hold, now, true, true, have ? &candidate : NULL);
          alert_buzzer_safety_level(d.level);
          publish_snapshot(&d, &hold, &sniff, now, radar_error, &capture);
        }
      }
    }
    d = ew_hold_update(&hold, now, had_bytes, false, NULL);
    /* This setter only updates the already-started buzzer worker's floor.
     * No logging, LVGL, files, AT calls or Agent dispatch on the safety path. */
    alert_buzzer_safety_level(d.level);
    publish_snapshot(&d, &hold, &sniff, now, radar_error, &capture);
    usleep(EW_SAFETY_PERIOD_MS * 1000u);
  }
  return NULL;
}

int ew_safety_start(void)
{
  pthread_t thread;
  pthread_attr_t attr;
  int ret;
  pthread_mutex_lock(&g_lock);
  if (g_started) {
    pthread_mutex_unlock(&g_lock);
    return 0;
  }
  ret = alert_buzzer_prepare();
  if (ret != 0) {
    pthread_mutex_unlock(&g_lock);
    return ret > 0 ? -ret : ret;
  }
  memset(&g_snapshot, 0, sizeof(g_snapshot));
  g_snapshot.decision.reason = "no_uart";
  g_snapshot.decision.ttc_s = -1.0f;
  g_snapshot.decision.link = EW_LINK_DEAD;
  g_event_head = g_event_count = 0;
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 8192);
#ifdef __NuttX__
  {
    struct sched_param param;
    memset(&param, 0, sizeof(param));
    param.sched_priority = 120;
    pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);
    pthread_attr_setschedparam(&attr, &param);
  }
#endif
  ret = pthread_create(&thread, &attr, safety_worker, NULL);
  pthread_attr_destroy(&attr);
  if (ret == 0) {
    g_started = g_snapshot.running = true;
    pthread_detach(thread);
  }
  pthread_mutex_unlock(&g_lock);
  return ret == 0 ? 0 : -ret;
}

void ew_safety_snapshot(ew_safety_snapshot_t *out)
{
  if (out == NULL) return;
  pthread_mutex_lock(&g_lock);
  *out = g_snapshot;
  pthread_mutex_unlock(&g_lock);
}

bool ew_safety_take_event(ew_safety_event_t *out)
{
  bool have = false;
  if (out == NULL) return false;
  pthread_mutex_lock(&g_lock);
  if (g_event_count != 0) {
    *out = g_events[g_event_head];
    g_event_head = (g_event_head + 1u) % EW_SAFETY_EVENTS;
    g_event_count--;
    have = true;
  }
  pthread_mutex_unlock(&g_lock);
  return have;
}
#else
int ew_safety_start(void) { return -ENOSYS; }
void ew_safety_snapshot(ew_safety_snapshot_t *out)
{
  if (out != NULL) {
    memset(out, 0, sizeof(*out));
    out->decision.ttc_s = -1.0f;
    out->decision.reason = "not_running";
  }
}
bool ew_safety_take_event(ew_safety_event_t *out) { (void)out; return false; }
#endif
