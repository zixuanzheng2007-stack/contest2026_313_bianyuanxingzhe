# SPDX-License-Identifier: Apache-2.0
"""Compile the production snapshot serializer and console handler, without hardware."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"

HARNESS = r'''
#include "ew_snapshot.h"
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static ew_safety_snapshot_t current;
void ew_safety_snapshot(ew_safety_snapshot_t *out) { *out = current; }
'''

MAIN = r'''
static void valid_state(void) {
  memset(&current, 0, sizeof(current));
  current.running = true;
  current.ever_frame = true;
  current.ever_bytes = true;
  current.decision.link = EW_LINK_OK;
  current.decision.level = EW_ALERT_STRONG;
  current.decision.range_m = 8.75f;
  current.decision.speed_kmh = 22.0f;
  current.event_id = 41;
  current.updated_ms = 123456u;
}
int main(int argc, char **argv) {
  char line[256], small[8], output[512];
  const char *invalid[] = {"", "bad id", "x\"", "x\\", "x\n", "x;id",
    "012345678901234567890123456789012345678901234567890"};
  unsigned i;
  valid_state();
  if (argc > 1 && !strncmp(argv[1], "--stdio", 7)) {
    fprintf(stderr, "SNAPSHOT_FIXTURE_ONLY: no physical board\n");
    if (!strcmp(argv[1], "--stdio-waiting")) {
      current.ever_frame = false;
      current.ever_bytes = false;
      current.decision.link = EW_LINK_DEAD;
      current.decision.level = EW_ALERT_NONE;
    }
    while (fgets(line, sizeof(line), stdin)) {
      size_t length = strlen(line);
      while (length && (line[length-1] == '\r' || line[length-1] == '\n'))
        line[--length] = '\0';
      if (!strncmp(line, "@snapshot ", 10)) ctl_snapshot(line + 10);
    }
    return 0;
  }
  assert(ew_snapshot_format(NULL, 1, "a", &current, 1) == -EINVAL);
  assert(ew_snapshot_format(output, 0, "a", &current, 1) == -EINVAL);
  assert(ew_snapshot_format(output, sizeof(output), NULL, &current, 1) == -EINVAL);
  assert(ew_snapshot_format(output, sizeof(output), "a", NULL, 1) == -EINVAL);
  assert(ew_snapshot_format(output, sizeof(output), "a", &current, 0) == -EINVAL);
  for (i=0; i<sizeof(invalid)/sizeof(invalid[0]); i++) {
    strcpy(output, "old contents");
    assert(ew_snapshot_format(output, sizeof(output), invalid[i], &current, 1) == -EINVAL);
    assert(output[0] == '\0');
  }
  assert(ew_snapshot_format(small, sizeof(small), "a", &current, 1) == -ENOSPC);
  assert(small[0] == '\0');
  ctl_snapshot("valid-1_A");
  current.decision.link = EW_LINK_DEAD;
  ctl_snapshot("stale");
  valid_state(); current.ever_frame = false; current.ever_bytes = false;
  ctl_snapshot("waiting");
  valid_state(); current.ever_frame = false; current.ever_bytes = true;
  ctl_snapshot("no_frame");
  valid_state(); current.radar_error = 5;
  ctl_snapshot("error");
  valid_state(); current.running = false;
  ctl_snapshot("stopped");
  valid_state(); current.decision.range_m = NAN;
  ctl_snapshot("nan-range");
  valid_state(); current.decision.speed_kmh = INFINITY;
  ctl_snapshot("nan-speed");
  valid_state(); current.decision.range_m = 0;
  ctl_snapshot("empty");
  valid_state(); current.decision.level = (ew_alert_level_t)99;
  ctl_snapshot("bad-level");
  valid_state(); ctl_snapshot("bad id");
  ctl_snapshot("last");
  return 0;
}
'''


def build_snapshot_fixture(directory: Path) -> Path:
    """Return an executable that uses the real formatter/handler with fixture state."""
    source = (SOURCE / "ew_serial_ctl.c").read_text(encoding="utf-8")
    handler = source[source.index("static void ctl_snapshot("):
                     source.index("static void ctl_dispatch(")]
    cfile = directory / "snapshot_fixture.c"
    exe = directory / "snapshot_fixture.exe"
    cfile.write_text(HARNESS + handler + MAIN, encoding="utf-8")
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                    str(cfile), str(SOURCE / "ew_snapshot.c"), "-o", str(exe)], check=True)
    return exe


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_snapshot_")
        cls.exe = build_snapshot_fixture(Path(cls.temp.name))
        output = subprocess.check_output([str(cls.exe)], text=True)
        cls.rows = [json.loads(line.split("[ew-snapshot] ", 1)[1])
                    for line in output.splitlines()]
        cls.by_id = {row["id"]: row for row in cls.rows if row.get("id") is not None}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_handler_preserves_clock_event_and_nullable_config(self):
        row = self.by_id["valid-1_A"]
        self.assertEqual(row["origin"], "device")
        self.assertEqual(row["range_m"], 8.75)
        self.assertEqual(row["speed_kmh"], 22)
        self.assertEqual(row["event_id"], 41)
        self.assertEqual(row["updated_ms"], 123456)
        self.assertEqual(row["clock"], "device_monotonic")
        self.assertIsNone(row["profile"])
        self.assertEqual(row["snapshot_seq"], 1)

    def test_stale_waiting_errors_do_not_fabricate_measurements(self):
        for name, link in (("stale", "stale"), ("waiting", "waiting"),
                           ("no_frame", "no_frame"), ("error", "error"),
                           ("stopped", "error")):
            row = self.by_id[name]
            self.assertEqual(row["radar_link"], link)
            self.assertEqual(row["alert_level"], "strong")
            self.assertIsNone(row["range_m"])
            self.assertIsNone(row["speed_kmh"])
        self.assertIsNone(self.by_id["nan-range"]["range_m"])
        self.assertIsNone(self.by_id["nan-speed"]["speed_kmh"])
        self.assertIsNone(self.by_id["empty"]["range_m"])

    def test_invalid_output_never_publishes_partial_json(self):
        errors = [row for row in self.rows if "error" in row]
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(row["id"] is None for row in errors))
        self.assertEqual(self.by_id["last"]["snapshot_seq"], 12)

    def test_console_fixture_answers_full_request_id(self):
        result = subprocess.run([str(self.exe), "--stdio"], input="@snapshot broker_001\r\n",
                                capture_output=True, text=True, check=True)
        self.assertIn("no physical board", result.stderr)
        row = json.loads(result.stdout.split("[ew-snapshot] ", 1)[1])
        self.assertEqual(row["id"], "broker_001")
        self.assertEqual(row["snapshot_seq"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
