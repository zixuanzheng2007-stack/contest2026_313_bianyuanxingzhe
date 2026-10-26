#!/usr/bin/env python3
"""Collect fresh read-only board snapshots on one explicitly selected UART.

Example: python scripts/host/board_snapshot_acceptance.py --port COM7 --count 10
Only @snapshot is transmitted at 1 Mbps, with DTR/RTS disabled before opening.
No port discovery, reset, flashing, AT, alert or model command is performed.
Ordinary console text is discarded by SerialBroker and never saved here.

A successful report proves only the snapshot protocol: waiting radar state,
an alert enum, or an open COM port does not prove detection, sound or light.
Supplied firmware version/SHA256 are operator claims, not flash-readback proof.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Callable

from mobile_serial_gateway import GatewayError, SerialBroker

ROOT = Path(__file__).resolve().parents[2]
BAUD_RATE = 1_000_000
DISPLAY_ZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _now() -> str:
    return datetime.now(DISPLAY_ZONE).isoformat()


def _validate_options(count: int, timeout_s: float, interval_s: float,
                      firmware_version: str | None, firmware_sha256: str | None) -> None:
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("count must be an integer from 1 to 1000")
    for name, value, minimum, maximum in (("timeout", timeout_s, 0.05, 5),
                                          ("interval", interval_s, 0, 60)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not minimum <= value <= maximum):
            raise ValueError(f"{name} must be between {minimum} and {maximum} seconds")
    if firmware_version is not None and (not isinstance(firmware_version, str)
                                        or not firmware_version.strip()
                                        or len(firmware_version) > 256
                                        or any(ord(character) < 32 for character in firmware_version)):
        raise ValueError("firmware-version must be nonempty text without controls, at most 256 characters")
    if firmware_sha256 is not None and (not isinstance(firmware_sha256, str)
                                       or not re.fullmatch(r"[0-9a-fA-F]{64}", firmware_sha256)):
        raise ValueError("firmware-sha256 must contain exactly 64 hexadecimal digits")


def _new_report(*, port_label: str, count: int, timeout_s: float, interval_s: float,
                 firmware_version: str | None, firmware_sha256: str | None,
                 transport_kind: str) -> dict[str, Any]:
    return {
        "report_version": 1,
        "scope": "read_only_snapshot_protocol",
        "started_at": _now(),
        "display_timezone": "Asia/Shanghai",
        "passed": False,
        "transport": transport_kind,
        "port": port_label,
        "baud_rate": BAUD_RATE,
        "dtr": False,
        "rts": False,
        "requested_count": count,
        "timeout_s": timeout_s,
        "interval_s": interval_s,
        "commands_allowed": ["@snapshot <generated_request_id>"],
        "firmware": {
            "version_claim": firmware_version,
            "sha256_claim": firmware_sha256.lower() if firmware_sha256 else None,
            "claim_source": "operator_supplied" if firmware_version or firmware_sha256 else "not_supplied",
            "identity_verified": False,
        },
        "samples": [],
        "verification": {
            "snapshot_protocol": False,
            "radar_ready_in_all_samples": False,
            "alert_execution": False,
            "physical_sound_or_light": False,
            "wireless_control": False,
            "road_performance": False,
        },
        "interpretation": (
            "Success means fresh valid snapshots only. connected is protocol connectivity; "
            "waiting/stale/null measurements do not prove radar detection. Alert level is "
            "reported software state, not actuator evidence. Firmware claims are unverified."
        ),
    }


def _finish_report(report: dict[str, Any]) -> dict[str, Any]:
    samples = report["samples"]
    complete = len(samples) == report["requested_count"] and "error" not in report
    report["passed"] = complete
    report["verification"]["snapshot_protocol"] = complete
    report["verification"]["radar_ready_in_all_samples"] = (
        complete and all(sample["radar_link"] == "ok" for sample in samples)
    )
    report["summary"] = {
        "valid_snapshots": len(samples),
        "fresh_sequences": [sample["snapshot_seq"] for sample in samples],
        "radar_link_counts": dict(Counter(sample["radar_link"] for sample in samples)),
        "alert_level_counts": dict(Counter(sample["alert_level"] for sample in samples)),
        "null_measurement_samples": sum(sample["range_m"] is None or sample["speed_kmh"] is None
                                          for sample in samples),
    }
    report["finished_at"] = _now()
    return report


def run_acceptance(serial_port: Any, *, port_label: str, count: int = 10,
                   timeout_s: float = 0.8, interval_s: float = 0.1,
                   firmware_version: str | None = None, firmware_sha256: str | None = None,
                   transport_kind: str = "fixture") -> dict[str, Any]:
    """Use the real broker on an explicitly provided transport, closing it after use.

    Tests and software fixtures should retain transport_kind="fixture". The CLI
    sets "serial" only after opening the operator-selected serial device.
    Failure stops collection; no retry bridges a reboot into one claimed run.
    """
    _validate_options(count, timeout_s, interval_s, firmware_version, firmware_sha256)
    if not isinstance(port_label, str) or not port_label or any(ord(c) < 32 for c in port_label):
        raise ValueError("port_label must be nonempty text without controls")
    if transport_kind not in {"serial", "fixture"}:
        raise ValueError("transport_kind must be serial or fixture")
    report = _new_report(port_label=port_label, count=count, timeout_s=timeout_s,
                         interval_s=interval_s, firmware_version=firmware_version,
                         firmware_sha256=firmware_sha256, transport_kind=transport_kind)
    broker = None
    try:
        broker = SerialBroker(serial_port, timeout_s=timeout_s, max_pending=1)
        previous_seq = None
        for index in range(1, count + 1):
            state = broker.query()
            sequence = state["snapshot_seq"]
            if previous_seq is not None and sequence <= previous_seq:
                raise GatewayError("stale_snapshot", "Snapshot sequence did not advance.")
            previous_seq = sequence
            # Deliberate allowlist: no raw console text, request buffer or
            # unexpected firmware properties can enter the evidence file.
            sample = {name: state[name] for name in (
                "connected", "snapshot_seq", "event_id", "radar_link", "range_m",
                "speed_kmh", "alert_level", "updated_ms", "clock", "received_at_ms", "radar_error",
            )}
            sample["sample_index"] = index
            report["samples"].append(sample)
            if index < count and interval_s:
                time.sleep(interval_s)
    except GatewayError as exc:
        report["error"] = {"code": exc.code, "message": str(exc),
                           "sample_index": len(report["samples"]) + 1}
    except (OSError, IOError) as exc:
        report["error"] = {"code": "serial_io_error", "message": "Serial transport failed.",
                           "exception_type": type(exc).__name__,
                           "sample_index": len(report["samples"]) + 1}
    finally:
        if broker is not None:
            broker.close()
        else:
            serial_port.close()
    return _finish_report(report)


def write_report(report: dict[str, Any], path: Path) -> None:
    """Publish one complete JSON report; no serial/console transcript is written."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    try:
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _open_serial(port_name: str):
    import serial  # Optional dependency is needed only for explicit CLI hardware use.
    port = serial.Serial(port=None, baudrate=BAUD_RATE, timeout=0.05, write_timeout=0.2)
    try:
        port.dtr = False
        port.rts = False
        port.port = port_name
        port.open()
    except Exception:
        port.close()
        raise
    return port


def main(argv: list[str] | None = None, *, serial_factory: Callable[[str], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Explicit serial device, e.g. COM7; never scanned")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=0.8, help="Per-snapshot deadline, 0.05-5 seconds")
    parser.add_argument("--interval", type=float, default=0.1, help="Delay between snapshots, 0-60 seconds")
    parser.add_argument("--firmware-version", help="Operator-supplied version claim; not independently verified")
    parser.add_argument("--firmware-sha256", help="Operator-supplied image hash; does not prove flashed bytes")
    parser.add_argument("--output", type=Path, help="JSON evidence path (default is a unique artifacts file)")
    args = parser.parse_args(argv)
    try:
        _validate_options(args.count, args.timeout, args.interval, args.firmware_version, args.firmware_sha256)
        if not args.port.strip() or any(ord(c) < 32 for c in args.port):
            raise ValueError("port must be explicit nonempty text without controls")
    except ValueError as exc:
        parser.error(str(exc))
    output = args.output or ROOT / "VMware_share/artifacts" / (
        "board_snapshot_acceptance_" + datetime.now(DISPLAY_ZONE).strftime("%Y%m%d_%H%M%S")
        + "_" + secrets.token_hex(3) + ".json")
    kind = "fixture" if serial_factory is not None else "serial"
    metadata = dict(port_label=args.port, count=args.count, timeout_s=args.timeout,
                    interval_s=args.interval, firmware_version=args.firmware_version,
                    firmware_sha256=args.firmware_sha256, transport_kind=kind)
    try:
        port = (serial_factory or _open_serial)(args.port)
    except (ImportError, OSError, IOError) as exc:
        report = _new_report(**metadata)
        report["error"] = {"code": "dependency_missing" if isinstance(exc, ImportError) else "serial_open_failed",
                           "message": "Selected serial device could not be opened; no command was sent.",
                           "exception_type": type(exc).__name__, "sample_index": 1}
        report = _finish_report(report)
    else:
        report = run_acceptance(port, **metadata)
    try:
        write_report(report, output)
    except (OSError, ValueError) as exc:
        print("REPORT_WRITE_FAILED: " + type(exc).__name__)
        return 2
    summary = report["summary"]
    print(("PASS" if report["passed"] else "FAIL")
          + f" snapshot protocol: {summary['valid_snapshots']}/{args.count}; "
          + "radar links=" + json.dumps(summary["radar_link_counts"], sort_keys=True))
    print("Actuator/sound/light, wireless and firmware identity remain unverified.")
    print("REPORT " + str(output.resolve()))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
