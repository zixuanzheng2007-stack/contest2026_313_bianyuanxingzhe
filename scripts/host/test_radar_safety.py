# SPDX-License-Identifier: Apache-2.0
"""Compile production C and verify synthetic radar safety/replay on any host."""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from radar_replay import build_replay

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"
FIXTURE = Path(__file__).parent / "fixtures/radar_safety/synthetic_sequence.csv"


def frame(*targets: tuple[int, int, int, int, int], alarm: int = 0) -> bytes:
    body = bytes((len(targets), alarm)) + b"".join(bytes(target) for target in targets)
    return bytes.fromhex("f4f3f2f1") + len(body).to_bytes(2, "little") + body + bytes.fromhex("f8f7f6f5")


def input_csv(rows: list[tuple[int, bytes]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("timestamp_ms", "raw_hex"))
    writer.writerows((stamp, data.hex(" ")) for stamp, data in rows)
    return output.getvalue()


class RadarSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            raise RuntimeError("GCC required: cannot skip safety regressions")
        os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ.get("PATH", "")
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_radar_safety_")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name)
        cls.replay = {}
        cls.smoke = {}
        for confirm in (1, 3):
            folder = cls.path / str(confirm)
            folder.mkdir()
            cls.replay[confirm] = build_replay(folder, confirm)
            exe = folder / ("host_smoke.exe" if os.name == "nt" else "host_smoke")
            subprocess.run([
                compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                f"-DEW_CONFIRM_FRAMES={confirm}", str(SOURCE / "host_smoke.c"),
                str(SOURCE / "ew_ld2451.c"), "-o", str(exe), "-lm",
            ], check=True)
            cls.smoke[confirm] = exe

    def replay_rows(self, rows: list[tuple[int, bytes]], confirm: int = 1) -> list[dict[str, str]]:
        result = subprocess.run([str(self.replay[confirm]), "-"], input=input_csv(rows),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return list(csv.DictReader(io.StringIO(result.stdout)))

    def test_production_parser_decide_hold_default_and_three_fresh_frames(self) -> None:
        for confirm, executable in self.smoke.items():
            with self.subTest(confirm=confirm):
                result = subprocess.run([str(executable)], text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("ALL PASS", result.stdout)

    def test_synthetic_fixture_fragments_noise_multi_target_and_timing(self) -> None:
        result = subprocess.run([str(self.replay[1]), str(FIXTURE)],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual([r["level"] for r in rows],
                         ["NONE", "NONE", "SOFT", "EMERGENCY", "EMERGENCY", "EMERGENCY", "NONE", "NONE"])
        self.assertEqual([r["link"] for r in rows],
                         ["NOISE", "NOISE", "OK", "OK", "OK", "OK", "OK", "DEAD"])
        self.assertEqual(rows[3]["range_m"], "20.000")
        self.assertEqual(rows[3]["frames_ok"], "2")

    def test_confirm_three_counts_each_frame_in_one_read_and_holds_metadata(self) -> None:
        emergency = frame((128, 6, 0, 40, 30))
        soft = frame((128, 22, 0, 20, 30))
        rows = self.replay_rows([(100, emergency * 3), (1000, soft),
                                 (1010, soft), (1020, soft), (1100, b""),
                                 (2019, b""), (2020, b"")], confirm=3)
        self.assertEqual(rows[0]["frames_in_row"], "3")
        self.assertEqual([r["level"] for r in rows],
                         ["EMERGENCY"] * 4 + ["SOFT", "SOFT", "NONE"])
        self.assertTrue(all(r["range_m"] == "6.000" for r in rows[:4]))
        self.assertEqual(rows[4]["range_m"], "22.000")

    def test_empty_fresh_frame_interrupts_confirmation_but_noise_does_not(self) -> None:
        alert = frame((128, 6, 0, 40, 30))
        empty = frame()
        rows = self.replay_rows([(0, alert), (1, b"\x99"), (2, alert),
                                 (3, empty), (4, alert), (5, alert), (6, alert)], confirm=3)
        self.assertEqual([r["pending_hits"] for r in rows], ["1", "1", "2", "0", "1", "2", "3"])
        self.assertEqual([r["level"] for r in rows], ["NONE"] * 6 + ["EMERGENCY"])

    def test_all_target_orders_have_same_highest_risk(self) -> None:
        near = (128, 12, 0, 5, 30)
        dangerous = (128, 20, 0, 120, 30)
        for targets in ((near, dangerous), (dangerous, near)):
            row = self.replay_rows([(1, frame(*targets))])[0]
            self.assertEqual((row["level"], row["range_m"]), ("EMERGENCY", "20.000"))
        for batch in (frame(near) + frame(dangerous), frame(dangerous) + frame(near)):
            row = self.replay_rows([(1, batch)])[0]
            self.assertEqual((row["level"], row["range_m"]), ("EMERGENCY", "20.000"))

    def test_recorded_zero_body_heartbeat_is_empty_not_noise(self) -> None:
        # Actual COM7 sample and HLK V1.03 section 1.3, not invented target data.
        empty = bytes.fromhex("f4f3f2f10000f8f7f6f5")
        rows = self.replay_rows([(0, empty[:6]), (1, empty[6:]),
                                 (2, empty * 3), (1002, empty), (2503, b"")])
        self.assertEqual([r["frames_ok"] for r in rows], ["0", "1", "4", "5", "5"])
        self.assertTrue(all(r["frames_bad"] == "0" for r in rows))
        self.assertEqual([r["link"] for r in rows], ["NOISE", "OK", "OK", "OK", "DEAD"])
        self.assertTrue(all(r["level"] == "NONE" for r in rows))

    def test_zero_body_still_requires_valid_tail_and_restarts_confirmation(self) -> None:
        empty = bytes.fromhex("f4f3f2f10000f8f7f6f5")
        malformed = empty[:-1] + b"\x00"
        alert = frame((128, 6, 0, 40, 30))
        rows = self.replay_rows([(0, malformed), (1, alert), (2, alert),
                                 (3, empty), (4, alert), (5, alert), (6, alert)], confirm=3)
        self.assertEqual(rows[0]["frames_ok"], "0")
        self.assertGreaterEqual(int(rows[0]["frames_bad"]), 1)
        self.assertEqual([r["pending_hits"] for r in rows[1:]], ["1", "2", "0", "1", "2", "3"])
        self.assertEqual([r["level"] for r in rows], ["NONE"] * 6 + ["EMERGENCY"])

    def test_malformed_bytes_resynchronize_without_freshening_bad_frames(self) -> None:
        good = frame((128, 22, 0, 20, 30))
        rng = random.Random(20261021)
        noise = bytes(rng.randrange(0, 240) for _ in range(512))
        malformed = bytearray(good)
        malformed[6] = 2
        rows = self.replay_rows([(0, noise + malformed), (10, good),
                                 (1520, malformed), (1521, b"")])
        self.assertEqual(rows[0]["frames_ok"], "0")
        self.assertGreaterEqual(int(rows[0]["frames_bad"]), 1)
        self.assertEqual(rows[1]["frames_ok"], "1")
        self.assertEqual(rows[2]["frames_ok"], "1")
        self.assertEqual(rows[2]["link"], "NOISE")
        self.assertEqual(rows[2]["level"], "NONE")

    def test_uint32_wrap_and_exact_clear_stale_boundaries(self) -> None:
        alert = frame((128, 6, 0, 40, 30))
        first = 0xFFFFFF00
        wrap = lambda delta: (first + delta) & 0xFFFFFFFF
        rows = self.replay_rows([(first, alert), (wrap(999), b""),
                                 (wrap(1000), b""), (wrap(1500), b""), (wrap(1501), b"")])
        self.assertEqual([r["level"] for r in rows], ["EMERGENCY", "EMERGENCY", "NONE", "NONE", "NONE"])
        self.assertEqual([r["link"] for r in rows], ["OK", "OK", "OK", "OK", "DEAD"])

    def test_input_schema_rejects_errors_with_nonzero_exit(self) -> None:
        invalid = ["", "timestamp,raw\n0,00\n", "timestamp_ms,raw_hex\n",
                   "timestamp_ms,raw_hex\n-1,\n", "timestamp_ms,raw_hex\n4294967296,\n",
                   "timestamp_ms,raw_hex\n0,F\n", "timestamp_ms,raw_hex\n0,GG\n",
                   "timestamp_ms,raw_hex\n0,00,extra\n", 'timestamp_ms,raw_hex\n0,"00\n',
                   "timestamp_ms,raw_hex\n2,\n1,\n", "timestamp_ms,raw_hex\n0,\n2147483648,\n"]
        for data in invalid:
            with self.subTest(data=data):
                result = subprocess.run([str(self.replay[1]), "-"], input=data,
                                        text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("host_replay:", result.stderr)
        result = subprocess.run([str(self.replay[1]), str(self.path / "missing.csv")],
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)

    def test_python_cli_builds_real_c_and_writes_csv(self) -> None:
        output = self.path / "wrapper.csv"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("radar_replay.py")),
                                 str(FIXTURE), "--output", str(output)],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with output.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(rows[3]["level"], "EMERGENCY")
        self.assertIn("SYNTHETIC", FIXTURE.read_text(encoding="utf-8"))
        before = output.read_bytes()
        invalid = self.path / "invalid.csv"
        invalid.write_text("timestamp_ms,raw_hex\n0,broken\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("radar_replay.py")),
                                 str(invalid), "--output", str(output)],
                                text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
