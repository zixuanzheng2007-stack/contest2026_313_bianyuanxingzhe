# SPDX-License-Identifier: Apache-2.0
"""Road capture evidence validity, partial preservation and production C wire handler."""
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from roadtest_capture import Capture, VERSION

ROOT = Path(__file__).resolve().parents[2]


class FixturePort:
    def __init__(self, gap=False, dropped=0, broken=False, logger_stops=False,
                 ignores_shutdown=False):
        self.buffer = b""
        self.seq = 0
        self.enabled = False
        self.gap, self.dropped, self.broken = gap, dropped, broken
        self.logger_stops, self.ignores_shutdown = logger_stops, ignores_shutdown
        self.commands = []

    def write(self, data):
        verb, token, *action = data.decode().split()
        self.commands.append(verb)
        rows = []
        if verb == "@road":
            if action == ["on"]:
                self.enabled = True
            elif action == ["off"]:
                if not (self.ignores_shutdown and self.enabled):
                    self.enabled = False
            elif action == ["poll"] and self.enabled:
                self.seq += 2 if self.gap else 1
                rows.append({"id": token, "seq": self.seq, "timestamp_ms": 100 + self.seq * 20,
                             "raw_hex": "f4f3f2f10000f8f7f6f5"})
                if self.logger_stops:
                    self.enabled = False
            rows.append({"id": token, "end": True, "enabled": self.enabled,
                         "dropped": self.dropped, "pending": 0, "firmware": VERSION})
        elif verb == "@sensitivity":
            rows.append({"id": token, "ok": True, "profile": "standard"})
        elif verb == "@snapshot":
            if self.broken:
                raise OSError("fixture disconnected")
            rows.append({"id": token, "origin": "device", "clock": "device_monotonic",
                         "snapshot_seq": 1, "updated_ms": 120})
        prefix = verb[1:]
        self.buffer += ("unrelated credential must not be saved\n" + "\n".join(
            f"[ew-{prefix}] " + json.dumps(row) for row in rows) + "\n").encode()

    def flush(self):
        pass

    def read(self, size):
        # Split wire replies to exercise the real line assembler.
        result, self.buffer = self.buffer[:31], self.buffer[31:]
        return result


class RoadCaptureTests(unittest.TestCase):
    def test_capture_preserves_replay_bytes_and_does_not_claim_road_success(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d) / "trial"
            port = FixturePort()
            report = Capture(port, directory, {"transport": "fixture"}).run(0.01)
            self.assertTrue(report["capture_complete"], report)
            self.assertFalse(report["road_performance_verified"])
            self.assertEqual(set(port.commands), {"@road", "@snapshot", "@sensitivity"})
            with (directory / "raw.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["raw_hex"], "f4f3f2f10000f8f7f6f5")
            self.assertNotIn("credential", (directory / "protocol.jsonl").read_text())
            with self.assertRaises(FileExistsError):
                Capture(port, directory, {})

    def test_gaps_drops_or_disconnect_keep_partial_evidence_but_fail(self):
        for kwargs in ({"gap": True}, {"dropped": 2}, {"broken": True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as d:
                directory = Path(d) / "partial"
                report = Capture(FixturePort(**kwargs), directory, {}).run(0.01)
                self.assertFalse(report["capture_complete"])
                self.assertTrue(report["records"])
                self.assertEqual(json.loads((directory / "session.json").read_text())["capture_complete"], False)

    def test_logger_stopping_during_poll_and_failed_off_keep_capture_incomplete(self):
        for kwargs in ({"logger_stops": True}, {"ignores_shutdown": True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as d:
                directory = Path(d) / "partial"
                report = Capture(FixturePort(**kwargs), directory, {}).run(0.01)
                self.assertFalse(report["capture_complete"])
                self.assertTrue(report["records"])
                self.assertTrue(report["errors"])
                self.assertFalse(json.loads((directory / "session.json").read_text())["capture_complete"])

    def test_host_replay_groups_same_timestamp_chunks_into_one_safety_poll(self):
        source = ROOT / "app/edge_walker"
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            compiler = shutil.which("gcc")
            self.assertIsNotNone(compiler)
            os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ["PATH"]
            exe = folder / ("host_replay.exe" if os.name == "nt" else "host_replay")
            subprocess.run([compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-DEW_CONFIRM_FRAMES=2", str(source / "host_replay.c"),
                            str(source / "ew_ld2451.c"), "-o", str(exe), "-lm"], check=True)
            frame = bytes.fromhex("f4f3f2f1 0700 01 00 80 06 00 28 1e f8f7f6f5")
            split = 6
            capture = folder / "chunks.csv"
            capture.write_text("timestamp_ms,raw_hex\n123," + frame[:split].hex(" ") +
                               "\n123," + frame[split:].hex(" ") + "\n", encoding="ascii")
            result = subprocess.run([str(exe), str(capture)], capture_output=True,
                                    text=True, check=True)
            rows = list(csv.DictReader(io.StringIO(result.stdout)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["input_bytes"], str(len(frame)))
            self.assertEqual(rows[0]["frames_in_row"], "1")
            self.assertEqual(rows[0]["frames_ok"], "1")
            self.assertEqual(rows[0]["frames_bad"], "0")
            self.assertEqual(rows[0]["link"], "OK")
            self.assertEqual(rows[0]["last_frame_level"], "EMERGENCY")
            self.assertEqual(rows[0]["pending_hits"], "1")
            self.assertEqual(rows[0]["level"], "NONE")

    def test_bad_raw_and_backwards_time_are_rejected_but_uint32_wrap_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            capture = Capture(FixturePort(), Path(d) / "trial", {})
            try:
                capture.record({"seq": 1, "timestamp_ms": 0xfffffff0, "raw_hex": ""})
                capture.record({"seq": 2, "timestamp_ms": 10, "raw_hex": "ff"})
                for row in ({"seq": 3, "timestamp_ms": 9, "raw_hex": "ff"},
                            {"seq": 3, "timestamp_ms": 11, "raw_hex": "a"},
                            {"seq": 2, "timestamp_ms": 11, "raw_hex": "ff"}):
                    with self.assertRaises(RuntimeError):
                        capture.record(row)
            finally:
                capture.evidence.close()
                capture.raw_file.close()

    def test_production_handler_and_bounded_ring_overflow(self):
        source = ROOT / "app/edge_walker"
        ctl = (source / "ew_serial_ctl.c").read_text(encoding="utf-8")
        handler = ctl[ctl.index("static void ctl_road("):ctl.index("static void ctl_radar_diag(")]
        # Use actual parser helpers, not a Python reconstruction of command syntax.
        # Find exact helper ends by brace count, avoiding dependencies on following UI code.
        def extract(name):
            start = ctl.index("static void " + name + "(")
            brace = ctl.index("{", start)
            depth = 1
            end = brace + 1
            while depth:
                depth += (ctl[end] == "{") - (ctl[end] == "}")
                end += 1
            return ctl[start:end]
        code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "ew_safety.c"
int alert_buzzer_prepare(void) { return 0; }
void alert_buzzer_safety_level(ew_alert_level_t level) { (void)level; }
unsigned long ew_agent_next_event_id(void) { return 1; }
'''
        code += extract("skip_spaces") + extract("parse_token") + handler
        code += r'''
int main(void) {
  unsigned i; uint8_t raw[64]; ew_road_record_t record;
  for(i=0;i<64;i++) raw[i]=(uint8_t)i;
  road_capture(raw,64,1); assert(!ew_safety_road_take(&record));
  ctl_road("start on");
  for(i=0;i<140;i++) road_capture(raw,64,i);
  assert(g_road_count==128 && g_road_dropped==12);
  ctl_road("poll1 poll"); assert(g_road_count==96);
  ctl_road("stop off");
  road_capture(raw,64,999); assert(g_road_count==96);
  ctl_road("bad poll extra");
  ctl_road("new on"); assert(g_road_count==0 && g_road_dropped==0);
  road_capture(NULL,0,1000); ctl_road("idle poll");
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            cfile = folder / "test.c"
            cfile.write_text(code, encoding="utf-8")
            compiler = shutil.which("gcc")
            self.assertIsNotNone(compiler)
            os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ["PATH"]
            exe = folder / ("test.exe" if os.name == "nt" else "test")
            subprocess.run([compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                            "-DEW_SAFETY_HOST_TEST", *(["-DO_NONBLOCK=0"] if os.name == "nt" else []),
                            "-I", str(source), str(cfile), str(source / "ew_ld2451.c"),
                            "-o", str(exe), "-lm"], check=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
            rows = [json.loads(line.split("[ew-road] ")[1]) for line in result.stdout.splitlines()]
            chunks = [r for r in rows if r.get("id") == "poll1" and "seq" in r]
            self.assertEqual(len(chunks), 32)
            self.assertEqual(chunks[0]["seq"], 13)
            self.assertEqual(chunks[0]["raw_hex"], bytes(range(64)).hex())
            self.assertTrue(any(r.get("id") == "idle" and r.get("raw_hex") == "" for r in rows))
            self.assertTrue(any(r.get("error") == "invalid_request" for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
