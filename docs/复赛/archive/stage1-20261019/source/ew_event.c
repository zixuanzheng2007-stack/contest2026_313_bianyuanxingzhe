/****************************************************************************
 * Event id and source helpers shared by every alert entry point.
 ****************************************************************************/

#include "ew_event.h"

#include <stdio.h>
#include <string.h>
#include <time.h>

static uint32_t g_event_seq;

const char *ew_event_source_name(ew_event_source_t source)
{
  switch (source) {
    case EW_EVENT_SOURCE_RADAR:
      return "radar";
    case EW_EVENT_SOURCE_FAKE:
      return "fake";
    case EW_EVENT_SOURCE_MANUAL:
      return "manual";
    case EW_EVENT_SOURCE_SERIAL:
      return "serial";
    case EW_EVENT_SOURCE_AGENT:
    default:
      return "agent";
  }
}

ew_event_source_t ew_event_source_parse(const char *name)
{
  if (name == NULL || name[0] == '\0') {
    return EW_EVENT_SOURCE_AGENT;
  }
  if (strcmp(name, "radar") == 0) {
    return EW_EVENT_SOURCE_RADAR;
  }
  if (strcmp(name, "fake") == 0) {
    return EW_EVENT_SOURCE_FAKE;
  }
  if (strcmp(name, "manual") == 0) {
    return EW_EVENT_SOURCE_MANUAL;
  }
  if (strcmp(name, "serial") == 0) {
    return EW_EVENT_SOURCE_SERIAL;
  }
  return EW_EVENT_SOURCE_AGENT;
}

void ew_event_make_id(char *out, size_t out_size, ew_event_source_t source)
{
  const char *tag;
  unsigned long stamp;
  unsigned long seq;

  if (out == NULL || out_size == 0) {
    return;
  }

  switch (source) {
    case EW_EVENT_SOURCE_RADAR:
      tag = "rad";
      break;
    case EW_EVENT_SOURCE_FAKE:
      tag = "fake";
      break;
    case EW_EVENT_SOURCE_MANUAL:
      tag = "man";
      break;
    case EW_EVENT_SOURCE_SERIAL:
      tag = "ser";
      break;
    case EW_EVENT_SOURCE_AGENT:
    default:
      tag = "agt";
      break;
  }

  stamp = (unsigned long)time(NULL);
  seq = (unsigned long)(++g_event_seq & 0xffffu);
  snprintf(out, out_size, "evt-%s-%08lx-%04lx", tag, stamp, seq);
}
