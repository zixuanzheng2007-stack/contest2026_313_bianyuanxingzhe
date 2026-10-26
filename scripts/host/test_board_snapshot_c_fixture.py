#!/usr/bin/env python3
"""Exercise acceptance through production C output over OS pipes, never a UART."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import unittest

from board_snapshot_acceptance import run_acceptance, write_report
from test_snapshot import SOURCE, build_snapshot_fixture


class SnapshotProcessTransport:
    """A bounded pipe adapter; every response is emitted by the compiled C fixture."""

    timeout = 0.05

    def __init__(self, executable: Path, mode: str, stderr):
        self.process = subprocess.Popen([str(executable), mode], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=stderr)
        self.messages: queue.Queue[bytes] = queue.Queue(maxsize=16)
        self.buffer = bytearray()
        self.writes: list[bytes] = []
        self.closed = False
        self.reader = threading.Thread(target=self._collect, daemon=True)
        self.reader.start()

    def _collect(self) -> None:
        while not self.closed:
            line = self.process.stdout.readline(8193)
            if not line:
                return
            try:
                self.messages.put(line, timeout=0.2)
            except queue.Full:
                return

    def write(self, data: bytes) -> int:
        if self.closed or self.process.poll() is not None:
            raise OSError("C fixture transport is closed")
        self.writes.append(data)
        count = self.process.stdin.write(data)
        self.process.stdin.flush()
        return count

    def read(self, size: int) -> bytes:
        if self.closed:
            raise OSError("C fixture transport is closed")
        if not self.buffer:
            try:
                self.buffer.extend(self.messages.get(timeout=self.timeout))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise OSError("C fixture process exited")
                return b""
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2)
        self.reader.join(timeout=2)
        self.process.stdout.close()


def collect_c_fixture_report(executable: Path, *, waiting: bool = False,
                             output: Path | None = None) -> tuple[dict, list[bytes]]:
    """Collect ten C snapshots and optionally publish explicitly labelled evidence."""
    mode = "--stdio-waiting" if waiting else "--stdio"
    with tempfile.TemporaryFile(mode="w+b") as stderr:
        transport = SnapshotProcessTransport(executable, mode, stderr)
        try:
            report = run_acceptance(transport, port_label="OS_PIPE_C_FIXTURE", count=10,
                                    timeout_s=1, interval_s=0, transport_kind="fixture")
        finally:
            transport.close()
        stderr.seek(0)
        marker = stderr.read()
    report["fixture"] = {
        "kind": "production_c_serializer_and_console_handler_over_os_pipes",
        "state": "waiting" if waiting else "fixed_valid_state",
        "board_tested": False,
        "physical_serial_opened": False,
        "marker_present": b"SNAPSHOT_FIXTURE_ONLY: no physical board" in marker,
        "process_exit_code": transport.process.returncode,
        "command_count": len(transport.writes),
        "source_sha256": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                          for name in ("ew_snapshot.c", "ew_snapshot.h", "ew_serial_ctl.c")},
    }
    if output is not None:
        write_report(report, output)
    return report, transport.writes


class BoardSnapshotCFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_snapshot_acceptance_c_")
        cls.exe = build_snapshot_fixture(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_ten_actual_c_responses_have_new_sequences_and_fixture_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "valid.json"
            report, writes = collect_c_fixture_report(self.exe, output=output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["fresh_sequences"], list(range(1, 11)))
        self.assertTrue(all(sample["event_id"] == 41 and sample["range_m"] == 8.75
                            and sample["speed_kmh"] == 22
                            and sample["updated_ms"] == 123456
                            and sample["clock"] == "device_monotonic"
                            for sample in report["samples"]))
        self.assertEqual(len(writes), 10)
        self.assertTrue(all(re.fullmatch(rb"@snapshot [A-Za-z0-9_-]{1,48}\r\n", command)
                            for command in writes))
        self.assertEqual(len(set(writes)), 10)
        self.assertEqual(report["transport"], "fixture")
        self.assertTrue(report["fixture"]["marker_present"])
        self.assertEqual(report["fixture"]["process_exit_code"], 0)
        self.assertFalse(report["fixture"]["board_tested"])
        self.assertFalse(report["fixture"]["physical_serial_opened"])
        self.assertFalse(report["firmware"]["identity_verified"])
        self.assertFalse(report["verification"]["alert_execution"])
        self.assertFalse(report["verification"]["physical_sound_or_light"])
        self.assertFalse(report["verification"]["wireless_control"])

    def test_waiting_c_state_passes_protocol_without_radar_or_actuation_claims(self):
        report, writes = collect_c_fixture_report(self.exe, waiting=True)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["fresh_sequences"], list(range(1, 11)))
        self.assertEqual(report["summary"]["null_measurement_samples"], 10)
        self.assertEqual(report["summary"]["radar_link_counts"], {"waiting": 10})
        self.assertTrue(all(sample["range_m"] is None and sample["speed_kmh"] is None
                            and sample["alert_level"] == "none"
                            for sample in report["samples"]))
        self.assertFalse(report["verification"]["radar_ready_in_all_samples"])
        self.assertFalse(report["verification"]["alert_execution"])
        self.assertEqual(len(writes), 10)
        self.assertTrue(report["fixture"]["marker_present"])
        self.assertEqual(report["fixture"]["process_exit_code"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
