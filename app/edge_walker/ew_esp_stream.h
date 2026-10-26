/* SPDX-License-Identifier: Apache-2.0 */
#ifndef EDGE_WALKER_ESP_STREAM_H
#define EDGE_WALKER_ESP_STREAM_H

#include <stddef.h>

#define EW_ESP_STREAM_DATA_MAX 8192u
#define EW_ESP_STREAM_LINE_MAX 512u
#define EW_ESP_STREAM_LINK_MAX 4u

typedef enum {
  EW_ESP_STREAM_LINE = 1,
  EW_ESP_STREAM_PROMPT,
  EW_ESP_STREAM_DATA
} ew_esp_stream_event_t;

/* Synchronous borrowed bytes, valid only during callback. DATA is emitted
 * once per complete +IPD frame, including binary NUL and embedded AT text.
 * link_id is -1 in single-link mode and 0..4 in multiple-link mode.
 * Callback must not re-enter the parser, perform I/O, or block. */
typedef void (*ew_esp_stream_callback_t)(void *context,
                                        ew_esp_stream_event_t event,
                                        int link_id,
                                        const unsigned char *bytes,
                                        size_t length);

/* Allocate in the owner's persistent storage, not a small task stack.
 * One parser per UART owner, no allocation, no I/O, no internal threads.
 * Supports normal transmission, active +IPD and CIPDINFO=0 only.
 * Invalid/oversized input poisons the session: further feed calls return the
 * same negative errno. The owner must close/invalidate connections before
 * init starts a NEW modem session. Never reset to resync an untrusted body. */
typedef struct {
  unsigned char buffer[EW_ESP_STREAM_DATA_MAX + 1u];
  size_t length;
  size_t expected;
  int link_id;
  int multiple;
  int error;
  int prompt_space;
  ew_esp_stream_callback_t callback;
  void *context;
} ew_esp_stream_t;

int ew_esp_stream_init(ew_esp_stream_t *parser, int multiple,
                        ew_esp_stream_callback_t callback, void *context);
int ew_esp_stream_feed(ew_esp_stream_t *parser,
                        const void *bytes, size_t length);

/* Called by the owner on an absolute partial-frame deadline, not an idle
 * timer extended by every byte. No deadline/clock is invented here.
 * Returns -ETIMEDOUT and poisons a partial line/frame; idle returns zero. */
int ew_esp_stream_expire(ew_esp_stream_t *parser);

#endif
