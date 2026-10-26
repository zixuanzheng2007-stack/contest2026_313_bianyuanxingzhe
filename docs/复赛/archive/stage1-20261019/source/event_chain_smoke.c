/****************************************************************************
 * Host-only Stage 1 contract smoke test.
 *
 * Verifies that fake/radar decisions enter one dispatcher, receive unique
 * event ids, and preserve the envelope through the Tool JSON bridge.
 ****************************************************************************/

#include "ew_agent.h"
#include "ew_agent_tool.h"
#include "ew_event.h"

#include <stdio.h>
#include <string.h>

static int g_output_count;
static char g_last_event_id[EW_EVENT_ID_SIZE];
static char g_last_source[EW_EVENT_SOURCE_SIZE];
static ew_alert_level_t g_last_level;

/* Replace the board output with a deterministic host recorder. */
void alert_output_event(const char *event_id, const char *source,
                        ew_alert_level_t level, const char *reason)
{
  g_output_count++;
  snprintf(g_last_event_id, sizeof(g_last_event_id), "%s",
           event_id ? event_id : "");
  snprintf(g_last_source, sizeof(g_last_source), "%s", source ? source : "");
  g_last_level = level;
  printf("  output event_id=%s source=%s level=%s reason=%s\n",
         g_last_event_id, g_last_source, ew_alert_level_name(level),
         reason ? reason : "");
}

static int expect(int condition, const char *message)
{
  if (!condition) {
    printf("FAIL %s\n", message);
    return 1;
  }
  printf("  PASS %s\n", message);
  return 0;
}

int main(void)
{
  ew_decision_t fake;
  ew_decision_t radar;
  char first_id[EW_EVENT_ID_SIZE];
  char tool_output[256];
  int fail = 0;

  memset(&fake, 0, sizeof(fake));
  fake.level = EW_ALERT_EMERGENCY;
  fake.range_m = 6.0f;
  fake.speed_kmh = 40.0f;
  fake.reason = "fake approaching";

  memset(&radar, 0, sizeof(radar));
  radar.level = EW_ALERT_SOFT;
  radar.range_m = 22.0f;
  radar.speed_kmh = 20.0f;
  radar.reason = "radar approaching";

  printf("edge_walker event_chain_smoke\n");
  fail += expect(ew_agent_emit_decision(&fake, EW_EVENT_SOURCE_FAKE) == 0,
                 "fake decision dispatched");
  snprintf(first_id, sizeof(first_id), "%s", g_last_event_id);
  fail += expect(g_output_count == 1, "fake reached output once");
  fail += expect(strncmp(first_id, "evt-fake-", 9) == 0,
                 "fake event id format");
  fail += expect(strcmp(g_last_source, "fake") == 0, "fake source preserved");
  fail += expect(g_last_level == EW_ALERT_EMERGENCY,
                 "fake level not rewritten");

  fail += expect(ew_agent_emit_decision(&radar, EW_EVENT_SOURCE_RADAR) == 0,
                 "radar decision dispatched");
  fail += expect(g_output_count == 2, "radar reached output once");
  fail += expect(strcmp(first_id, g_last_event_id) != 0,
                 "event ids are unique");
  fail += expect(strcmp(g_last_source, "radar") == 0,
                 "radar source preserved");
  fail += expect(g_last_level == EW_ALERT_SOFT,
                 "radar level not rewritten");

  memset(tool_output, 0, sizeof(tool_output));
  fail += expect(tool_approach_alert_execute(
                     "{\"event_id\":\"evt-ext-1\",\"source\":\"agent\","
                     "\"level\":\"strong\",\"reason\":\"host test\"}",
                     tool_output, sizeof(tool_output)) == 0,
                 "tool JSON executed");
  fail += expect(strcmp(g_last_event_id, "evt-ext-1") == 0,
                 "tool event id preserved");
  fail += expect(strcmp(g_last_source, "agent") == 0,
                 "tool source preserved");
  fail += expect(g_last_level == EW_ALERT_STRONG,
                 "tool level preserved");
  fail += expect(strstr(tool_output, "\"event_id\":\"evt-ext-1\"") != NULL,
                 "tool response returns event id");

  fail += expect(strcmp(ew_event_source_name(EW_EVENT_SOURCE_SERIAL),
                        "serial") == 0,
                 "source name mapping");

  if (fail == 0) {
    printf("EVENT CHAIN PASS\n");
    return 0;
  }
  printf("%d FAIL\n", fail);
  return 1;
}
