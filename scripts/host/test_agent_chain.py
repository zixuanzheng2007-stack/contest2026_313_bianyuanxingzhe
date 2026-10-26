"""Exercise the actual fake entry and local Agent/Tool/output chain ten times."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"


def main() -> None:
    # Compile the real command body without unrelated hardware commands.
    source = (SOURCE / "ew_main.c").read_text(encoding="utf-8")
    fake = source[source.index("static int cmd_fake("):source.index("/* NSH")]
    ctl_source = (SOURCE / "ew_serial_ctl.c").read_text(encoding="utf-8")
    ctl_fake = ctl_source[ctl_source.index("static void ctl_fake("):
                          ctl_source.index("static void *ctl_worker(")]
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ew_ld2451.h"
#include "ew_agent.h"
#include "ew_agent_tool.h"
''' + fake + ctl_fake + r'''
static int buzzer_calls, lcd_calls, lcd_result;
void alert_buzzer_level(ew_alert_level_t level) {
  assert(level == EW_ALERT_STRONG);
  buzzer_calls++;
}
int alert_lcd_show_event_checked(ew_alert_level_t level, const char *reason,
                          unsigned long event_id) {
  assert(level == EW_ALERT_STRONG);
  assert(reason != NULL && reason[0] != '\0');
  assert(event_id != 0 || lcd_result != 0);
  lcd_calls++;
  return lcd_result;
}
int alert_lcd_show_safety_event(ew_alert_level_t level, const char *reason,
                                unsigned long event_id) {
  return alert_lcd_show_event_checked(level, reason, event_id);
}
int main(void) {
  char *argv[] = {"ew", "fake", "10", "20"};
  const char *invalid[] = {NULL, "", "{}", "{\"level\":\"wrong\"}",
    "{\"level\":4}", "{\"level\":\"none\",\"level\":\"strong\"}",
    "{\"level\":\"strong\",\"event_id\":-1}", "{\"level\":\"none\"} extra"};
  char reply[128];
  int i;
  for (i = 0; i < (int)(sizeof(invalid) / sizeof(invalid[0])); i++) {
    assert(ew_agent_tool_execute(invalid[i], reply, sizeof(reply)) < 0);
    assert(strstr(reply, "\"ok\":false") != NULL);
  }
  assert(ew_agent_tool_approach_alert((ew_alert_level_t)99, "bad", reply, sizeof(reply)) < 0);
  assert(buzzer_calls == 0 && lcd_calls == 0);
  for (i = 0; i < 5; i++) assert(cmd_fake(4, argv) == 0);
  for (i = 0; i < 5; i++) ctl_fake(10.0f, 20.0f);
  assert(buzzer_calls == 10 && lcd_calls == 10);
  lcd_result = -EBUSY;
  assert(ew_agent_tool_approach_alert_event(EW_ALERT_STRONG, "busy", reply,
                                            sizeof(reply), 0) == -EBUSY);
  assert(strstr(reply, "\"ok\":false") && strstr(reply, "rejected"));
  lcd_result = 1;
  assert(ew_agent_tool_approach_alert_event(EW_ALERT_STRONG, "queue", reply,
                                            sizeof(reply), 0) == 0);
  assert(strstr(reply, "\"status\":\"queued\""));
  assert(ew_agent_emit_decision(NULL, EW_EVENT_SOURCE_MANUAL) < 0);
  return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ew_agent_chain_") as directory:
        path = Path(directory)
        cfile, exe = path / "test.c", path / "test.exe"
        cfile.write_text(harness, encoding="utf-8")
        subprocess.run([
            "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-variable",
            "-I", str(SOURCE), str(cfile),
            *(str(SOURCE / name) for name in (
                "ew_agent.c", "ew_agent_tool.c", "alert_output.c", "ew_ld2451.c",
                "ai_agent_ext/tool_approach_alert_ipc.c")),
            "-o", str(exe),
        ], check=True)
        output = subprocess.check_output([str(exe)], text=True)
    events = {}
    for event_id, stage in re.findall(r"\[ew_event\] event_id=(\d+) stage=(\w+)", output):
        events.setdefault(event_id, []).append(stage)
    assert len(events) == 10, output
    for stages in events.values():
        assert stages == ["decision", "agent", "tool", "alert_output", "complete"], output
    assert output.count("stage=complete result=0") == 10, output
    assert output.count("source=fake") == 5, output
    assert output.count("source=serial") == 5, output
    print("PASS: NSH and remote fake share 10 correlated Agent/Tool/output events and both actuators")


if __name__ == "__main__":
    main()
