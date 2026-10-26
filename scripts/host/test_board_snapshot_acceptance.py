#!/usr/bin/env python3
"""Read-only acceptance reports through the real broker and fake UART only."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from board_snapshot_acceptance import BAUD_RATE, _open_serial, main, run_acceptance, write_report
from test_mobile_serial_gateway import FakeSerial, board_snapshot, frame


class BoardSnapshotAcceptanceTests(unittest.TestCase):
    def test_ten_fresh_snapshots_preserve_event_ids_without_claiming_actuation(self):
        transport = FakeSerial()
        report = run_acceptance(transport, port_label="FAKE", interval_s=0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["scope"], "read_only_snapshot_protocol")
        self.assertEqual(report["transport"], "fixture")
        self.assertEqual(report["summary"]["fresh_sequences"], list(range(1, 11)))
        self.assertEqual(report["summary"]["valid_snapshots"], 10)
        self.assertTrue(all(sample["event_id"] == 41 for sample in report["samples"]))
        self.assertFalse(report["verification"]["alert_execution"])
        self.assertFalse(report["verification"]["physical_sound_or_light"])
        self.assertFalse(report["firmware"]["identity_verified"])
        self.assertEqual(report["firmware"]["claim_source"], "not_supplied")
        self.assertTrue(transport.closed)
        self.assertEqual(len(transport.writes), 10)
        self.assertTrue(all(re.fullmatch(rb"@snapshot [A-Za-z0-9_-]{1,48}\r\n", command)
                            for command in transport.writes))

    def test_waiting_null_is_protocol_success_but_not_radar_or_alert_success(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value.update(radar_link="waiting", range_m=None, speed_kmh=None, alert_level="none", event_id=0)
            return frame(value)
        report = run_acceptance(FakeSerial(response), port_label="FAKE", count=3, interval_s=0)
        self.assertTrue(report["passed"])
        self.assertTrue(report["verification"]["snapshot_protocol"])
        self.assertFalse(report["verification"]["radar_ready_in_all_samples"])
        self.assertFalse(report["verification"]["alert_execution"])
        self.assertEqual(report["summary"]["radar_link_counts"], {"waiting": 3})
        self.assertEqual(report["summary"]["null_measurement_samples"], 3)

    def test_timeout_stops_run_and_records_partial_evidence(self):
        def response(request_id, sequence):
            return frame(board_snapshot(request_id, sequence)) if sequence < 3 else None
        transport = FakeSerial(response)
        report = run_acceptance(transport, port_label="FAKE", timeout_s=0.07, interval_s=0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["valid_snapshots"], 2)
        self.assertEqual(report["error"]["sample_index"], 3)
        self.assertEqual(report["error"]["code"], "timeout")
        self.assertEqual(len(transport.writes), 3)
        self.assertTrue(transport.closed)

    def test_reboot_cannot_be_hidden_by_retries(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value.update(snapshot_seq=100 if sequence == 1 else 1,
                         updated_ms=10_000 if sequence == 1 else 1)
            return frame(value)
        transport = FakeSerial(response)
        report = run_acceptance(transport, port_label="FAKE", count=10, interval_s=0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["error"]["code"], "device_restarted")
        self.assertEqual(len(report["samples"]), 1)
        self.assertEqual(len(transport.writes), 2)

    def test_unsupported_firmware_cannot_generate_success(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value["v"] = 2
            return frame(value)
        report = run_acceptance(FakeSerial(response), port_label="FAKE", interval_s=0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["error"]["code"], "unsupported_firmware")
        self.assertEqual(report["samples"], [])

    def test_serial_disconnect_is_non_success_and_closes_transport(self):
        transport = FakeSerial()
        transport.fail = True
        report = run_acceptance(transport, port_label="FAKE", interval_s=0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["error"]["code"], "not_connected")
        self.assertTrue(transport.closed)

    def test_report_contains_no_console_noise_or_unexpected_firmware_fields(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value["api_key"] = "DO_NOT_RECORD"
            return b"@mimo-set SECRET_MUST_NOT_APPEAR\n" + frame(value)
        report = run_acceptance(FakeSerial(response), port_label="FAKE", count=2, interval_s=0)
        text = json.dumps(report)
        self.assertTrue(report["passed"])
        self.assertNotIn("DO_NOT_RECORD", text)
        self.assertNotIn("SECRET_MUST_NOT_APPEAR", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("@mimo-set", text)

    def test_firmware_metadata_is_only_operator_claim_and_clock_is_not_epoch(self):
        report = run_acceptance(FakeSerial(), port_label="FAKE", count=1, interval_s=0,
                                firmware_version="candidate-1", firmware_sha256="AB" * 32)
        self.assertEqual(report["firmware"]["version_claim"], "candidate-1")
        self.assertEqual(report["firmware"]["sha256_claim"], "ab" * 32)
        self.assertFalse(report["firmware"]["identity_verified"])
        self.assertEqual(report["samples"][0]["clock"], "device_monotonic")
        self.assertEqual(report["samples"][0]["updated_ms"], 1010)
        self.assertGreater(report["samples"][0]["received_at_ms"], 1_700_000_000_000)

    def test_invalid_options_rejected_before_any_query(self):
        invalid_cases = ({"count": 0}, {"count": True}, {"count": 1001},
                         {"timeout_s": float("nan")}, {"interval_s": -1},
                         {"firmware_sha256": "guess"}, {"firmware_version": "bad\nversion"},
                         {"transport_kind": "real_board_passed"})
        for options in invalid_cases:
            with self.subTest(options=options):
                transport = FakeSerial()
                with self.assertRaises(ValueError):
                    run_acceptance(transport, port_label="FAKE", **options)
                self.assertEqual(transport.writes, [])
                transport.close()

    def test_json_report_and_cli_return_nonzero_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            transport = FakeSerial()
            with redirect_stdout(io.StringIO()) as stream:
                result = main(["--port", "FAKE", "--count", "2", "--interval", "0", "--output", str(output)],
                              serial_factory=lambda port: transport)
            self.assertEqual(result, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual(report["transport"], "fixture")
            self.assertIn("snapshot protocol", stream.getvalue())
            self.assertFalse(list(Path(directory).glob("*.tmp-*")))
            failed = FakeSerial(lambda *_: None)
            with redirect_stdout(io.StringIO()):
                result = main(["--port", "FAKE", "--count", "2", "--timeout", "0.07",
                               "--interval", "0", "--output", str(output)], serial_factory=lambda port: failed)
            self.assertEqual(result, 1)
            self.assertFalse(json.loads(output.read_text(encoding="utf-8"))["passed"])

    def test_cli_open_failure_is_recorded_without_raw_exception_text(self):
        def fail_open(port):
            raise OSError("SECRET_LOCAL_DATA")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "error.json"
            with redirect_stdout(io.StringIO()):
                result = main(["--port", "FAKE", "--output", str(output)], serial_factory=fail_open)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(report["error"]["code"], "serial_open_failed")
            self.assertEqual(report["samples"], [])
            self.assertNotIn("SECRET_LOCAL_DATA", output.read_text())

    def test_serial_open_sets_baud_and_control_lines_before_open(self):
        class Port:
            def __init__(self, **options):
                self.options = options
                self.dtr = self.rts = True
                self.port = None
                self.opened = False
            def open(self):
                self.opened = True
                self.observed = (self.dtr, self.rts, self.port)
            def close(self):
                pass
        class Module:
            Serial = Port
        with patch.dict(sys.modules, {"serial": Module}):
            port = _open_serial("COM_TEST")
        self.assertEqual(port.options["baudrate"], BAUD_RATE)
        self.assertIsNone(port.options["port"])
        self.assertEqual(port.observed, (False, False, "COM_TEST"))
        self.assertTrue(port.opened)


if __name__ == "__main__":
    unittest.main(verbosity=2)
