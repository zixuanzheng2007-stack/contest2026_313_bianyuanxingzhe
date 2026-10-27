#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record opt-in board UART evidence and snapshots, one trial per new folder.

Only @road, @snapshot and @sensitivity get are sent. No reset, flashing,
simulation, actuator control or radar reconfiguration. Exit 0 means complete
protocol capture with no sequence gaps/drops, NOT successful road detection.
Raw CSV includes empty device ticks for genuine C parser/policy/Hold replay.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import re
import secrets
import time

VERSION = "ew-roadtest-20261028-rc1"
ZONE = timezone(timedelta(hours=8))


class Capture:
    def __init__(self, port, directory: Path, metadata: dict):
        directory.mkdir(parents=True, exist_ok=False)
        self.port = port
        self.directory = directory
        self.evidence = (directory / "protocol.jsonl").open("w", encoding="utf-8")
        self.raw_file = (directory / "raw.csv").open("w", encoding="utf-8", newline="")
        self.raw = csv.writer(self.raw_file)
        self.raw.writerow(["timestamp_ms", "raw_hex"])
        self.report = {"schema": 1, "metadata": metadata,
                       "started_at": datetime.now(ZONE).isoformat(),
                       "capture_complete": False, "road_performance_verified": False,
                       "firmware_identity": "device_reported_not_flash_readback",
                       "records": 0, "bytes": 0, "snapshots": 0, "dropped": 0,
                       "sequence_gaps": 0, "errors": []}
        self.last_seq = 0
        self.last_time = None
        self.pending = 0
        self.collection_active = False
        self.buffer = bytearray()

    def save(self, prefix: str, value):
        self.evidence.write(json.dumps({"host_monotonic_ns": time.monotonic_ns(),
                                       "host_time": datetime.now(ZONE).isoformat(),
                                       "kind": prefix, "data": value}, ensure_ascii=False) + "\n")
        self.evidence.flush()

    def request(self, verb: str, action: str = "", timeout: float = 2.0):
        token = secrets.token_hex(8)
        command = f"@{verb} {token}" + (f" {action}" if action else "") + "\r\n"
        self.port.write(command.encode("ascii"))
        self.port.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.port.read(4096)
            if not chunk:
                continue
            self.buffer.extend(chunk)
            if len(self.buffer) > 65536:
                raise RuntimeError("console line overflow; close screen mirror and other serial clients")
            while b"\n" in self.buffer:
                line, _, remaining = self.buffer.partition(b"\n")
                self.buffer = bytearray(remaining)
                text = line.decode("utf-8", "replace").strip()
                match = re.search(r"\[ew-(road|snapshot|sensitivity)\] (\{.*\})$", text)
                if not match:
                    # Only event stages; unrelated console/model/credential text is discarded.
                    event = re.search(r"\[(ew_event|ew_ipc)\] event_id=(\d+) stage=(\w+)", text)
                    if event:
                        self.save("event", {"channel": event[1], "event_id": int(event[2]), "stage": event[3]})
                    continue
                value = json.loads(match[2])
                if value.get("id") != token:
                    continue
                self.save(match[1], value)
                if verb == "road":
                    if value.get("end"):
                        if value.get("firmware") != VERSION:
                            raise RuntimeError("unexpected road logger firmware")
                        enabled = value.get("enabled")
                        if type(enabled) is not bool:
                            raise RuntimeError("road logger status missing")
                        self.report["dropped"] = max(self.report["dropped"], int(value["dropped"]))
                        self.pending = int(value["pending"])
                        if action == "on":
                            if not enabled:
                                raise RuntimeError("road logger did not enable")
                            self.collection_active = True
                        elif action == "off":
                            if enabled:
                                raise RuntimeError("road logger did not disable")
                            self.collection_active = False
                        elif action == "poll" and self.collection_active and not enabled:
                            raise RuntimeError("road logger stopped during active capture")
                        return value
                    self.record(value)
                else:
                    if verb == "snapshot":
                        if value.get("origin") != "device" or value.get("clock") != "device_monotonic":
                            raise RuntimeError("snapshot is not device evidence")
                        seq = value.get("snapshot_seq")
                        updated = value.get("updated_ms")
                        previous = self.report.get("last_snapshot_seq")
                        if type(seq) is not int or previous is not None and seq <= previous:
                            raise RuntimeError("stale snapshot or board restarted")
                        self.report["last_snapshot_seq"] = seq
                        self.report["last_snapshot_updated_ms"] = updated
                        self.report["snapshots"] += 1
                    return value
        raise TimeoutError(f"@{verb} {action} response timeout; partial evidence kept")

    def record(self, value):
        seq, stamp, raw = value["seq"], value["timestamp_ms"], value["raw_hex"]
        if type(seq) is not int or seq <= self.last_seq:
            raise RuntimeError("road sequence repeated or board restarted")
        if type(stamp) is not int or not 0 <= stamp <= 0xffffffff:
            raise RuntimeError("invalid device timestamp")
        if self.last_time is not None and (stamp - self.last_time) & 0xffffffff > 0x7fffffff:
            raise RuntimeError("device clock moved backwards")
        if not isinstance(raw, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}){0,64}", raw):
            raise RuntimeError("invalid raw UART evidence")
        self.report["sequence_gaps"] += seq - self.last_seq - 1
        self.last_seq, self.last_time = seq, stamp
        self.raw.writerow([stamp, raw])
        self.raw_file.flush()
        self.report["records"] += 1
        self.report["bytes"] += len(raw) // 2

    def run(self, duration: float):
        try:
            self.request("road", "off")
            profile = self.request("sensitivity", "get")
            if not profile.get("ok") or profile.get("profile") != "standard":
                raise RuntimeError("baseline requires standard profile; set it on device and start a new trial")
            self.report["profile"] = profile["profile"]
            self.request("road", "on")
            start = time.monotonic()
            snapshot_at = start
            while time.monotonic() - start < duration:
                cycle = time.monotonic()
                self.request("road", "poll")
                if cycle >= snapshot_at:
                    self.request("snapshot")
                    snapshot_at = time.monotonic() + 0.2
                if not self.pending:
                    time.sleep(max(0, 0.1 - (time.monotonic() - cycle)))
            self.report["requested_duration_s"] = duration
            self.report["actual_duration_s"] = time.monotonic() - start
        except (Exception, KeyboardInterrupt) as exc:
            self.report["errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                self.request("road", "off")
                for _ in range(8):
                    self.request("road", "poll")
                    if not self.pending:
                        break
                if self.pending:
                    raise RuntimeError("records remain undrained")
            except Exception as exc:
                self.report["errors"].append(f"shutdown: {exc}")
            self.report["capture_complete"] = bool(
                self.report["records"] and self.report["snapshots"] and
                not self.report["errors"] and not self.report["dropped"] and
                not self.report["sequence_gaps"])
            self.report["finished_at"] = datetime.now(ZONE).isoformat()
            self.evidence.close()
            self.raw_file.close()
            (self.directory / "session.json").write_text(
                json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit physical board COM port")
    parser.add_argument("--output", required=True, type=Path, help="new directory, never overwritten")
    parser.add_argument("--trial", required=True)
    parser.add_argument("--object", required=True, choices=["person", "bicycle", "none", "mixed"])
    parser.add_argument("--scenario", required=True, help="approach/away/crossing/parallel/etc")
    parser.add_argument("--speed-kmh", type=float, required=True, help="planned speed; NOT ground truth")
    parser.add_argument("--duration", type=float, default=45)
    parser.add_argument("--firmware-sha256", help="operator supplied package hash; not flash identity proof")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 3600:
        parser.error("duration must be 1..3600 seconds")
    if not math.isfinite(args.speed_kmh) or not 0 <= args.speed_kmh <= 50:
        parser.error("speed-kmh must be 0..50")
    if args.firmware_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.firmware_sha256):
        parser.error("firmware-sha256 must have 64 hex characters")
    if args.output.exists():
        parser.error("output already exists; select a new trial folder")
    import serial
    port = serial.Serial(port=None, baudrate=1_000_000, timeout=0.02, write_timeout=2)
    port.dtr = port.rts = False
    port.port = args.port
    metadata = {"trial": args.trial, "object": args.object, "scenario": args.scenario,
                "planned_speed_kmh": args.speed_kmh, "firmware_sha256_claim": args.firmware_sha256,
                "port": args.port, "transport": "physical_serial", "baud": 1_000_000}
    try:
        port.open()
        capture = Capture(port, args.output, metadata)
        print("Recording started. Keep video running; Ctrl+C saves partial evidence.", flush=True)
        report = capture.run(args.duration)
    finally:
        port.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["capture_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
