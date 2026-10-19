/****************************************************************************
 * B-side event envelope for the frozen approach-alert chain.
 *
 * A owns the safety decision. B assigns trace metadata so fake, radar and
 * manual triggers all enter the same registry -> Tool -> IPC -> output path.
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_EVENT_H
#define EDGE_WALKER_EW_EVENT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EW_EVENT_ID_SIZE 32
#define EW_EVENT_SOURCE_SIZE 16

typedef enum {
  EW_EVENT_SOURCE_RADAR = 0,
  EW_EVENT_SOURCE_FAKE,
  EW_EVENT_SOURCE_MANUAL,
  EW_EVENT_SOURCE_SERIAL,
  EW_EVENT_SOURCE_AGENT
} ew_event_source_t;

const char *ew_event_source_name(ew_event_source_t source);
ew_event_source_t ew_event_source_parse(const char *name);

/* Creates a process-local unique id, e.g. evt-rad-67f1a2b4-0001. */
void ew_event_make_id(char *out, size_t out_size, ew_event_source_t source);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_EVENT_H */
