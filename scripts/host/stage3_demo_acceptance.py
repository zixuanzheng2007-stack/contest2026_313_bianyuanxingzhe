#!/usr/bin/env python3
"""Run or review three continuous Edge Walker demonstrations.

Software chain checks are automated. Physical screen, buzzer, and radar checks
remain manual and are never inferred from serial logs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

EVENT_PATTERN = re.compile(r"\[ew_event\] event_id=(\d+) stage=(\w+)")
ERROR_PATTERN = re.compile(
    r"(?:assert|panic|segmentation fault|hardfault|stack overflow)",
    re.IGNORECASE,
)


def analyze_transcript(text: str, runs: int) -> dict:
    events: dict[str, list[str]] = {}
    for event_id, stage in EVENT_PATTERN.findall(text):
        events.setdefault(event_id, []).append(stage)
    chains = sum(
        stages == ["decision", "agent", "tool", "alert_output", "complete"]
        for stages in events.values()
    )
    checks = {
        "run_headers": text.count("=== STAGE3 RUN ") == runs,
        "goto_warn": text.count("[ew-ctl] goto warn") >= runs * 2,
        "goto_chat": text.count("[ew-ctl] goto chat") >= runs,
        "goto_wifi": text.count("[ew-ctl] goto wifi") >= runs,
        "fake_entry": text.count("[ew-ctl] fake ") >= runs,
        "agent_tool_chain": chains >= runs,
        "alert_output": text.count("[alert_output] level=") >= runs,
        "snapshot_response": text.count("[ew-snapshot] ") >= runs,
        "no_fatal_marker": ERROR_PATTERN.search(text) is None,
    }
    return {
        "software_chain": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "complete_event_chains": chains,
        "runs": runs,
        "physical_screen_buzzer_radar": "PENDING",
        "board_tested": False,
        "note": "Serial logs prove software dispatch only; observe the board manually.",
    }


def run_demo(port_name: str, runs: int) -> tuple[str, dict]:
    from serial_common import open_port, receive, send_line

    transcript = [
        "Stage-3 continuous demo acceptance",
        f"port={port_name} baud=1000000 dtr=0 rts=0 runs={runs}",
    ]
    with open_port(port_name) as port:
        transcript.append(receive(port, 1.0))
        for index in range(1, runs + 1):
            transcript.append(f"=== STAGE3 RUN {index}/{runs} ===")
            commands = (
                ("@goto warn", 2.0),
                ("@fake 1.0 40.0", 3.0),
                (f"@alert soft stage3-demo-{index}", 2.0),
                ("@goto chat", 1.0),
                ("@goto wifi", 1.0),
                ("@goto warn", 1.0),
                (f"@snapshot stage3-{index}", 2.0),
                ("@status", 24.0),
            )
            for command, wait in commands:
                transcript.extend((f">>> {command}", send_line(port, command, wait)))
    text = "\n".join(transcript)
    return text, analyze_transcript(text, runs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--replay", type=Path,
                        help="Analyze an existing transcript instead of opening a port")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    if args.replay:
        text = args.replay.read_text(encoding="utf-8")
        result = analyze_transcript(text, args.runs)
        log_path = args.output or args.replay.with_suffix(".analysis.json")
    else:
        from serial_common import artifact_path, write_log

        text, result = run_demo(args.port, args.runs)
        log_path = args.output or artifact_path("stage3_three_demos", ".json")
        write_log(artifact_path("stage3_three_demos", ".txt"), text)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **result,
    }
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"RESULT={log_path}")
    print(f"SOFTWARE_CHAIN={result['software_chain']}")
    print(f"COMPLETE_EVENT_CHAINS={result['complete_event_chains']}/{args.runs}")
    print("PHYSICAL_SCREEN_BUZZER_RADAR=PENDING")
    return 0 if result["software_chain"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
