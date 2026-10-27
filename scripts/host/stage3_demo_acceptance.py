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
    from mobile_serial_gateway import validate_snapshot, GatewayError
    headers = list(re.finditer(r"^=== STAGE3 RUN (\d+)/(\d+) ===$", text, re.M))
    valid_headers = (runs > 0 and len(headers) == runs and
                     [(int(h[1]),int(h[2])) for h in headers] == [(i,runs) for i in range(1,runs+1)])
    checks = {'run_headers':valid_headers, 'no_fatal_marker':ERROR_PATTERN.search(text) is None}
    chains = 0; previous_sequence = 0; previous_clock = -1; seen_ids = set()
    for index, header in enumerate(headers,1):
        end = headers[index].start() if index < len(headers) else len(text)
        part = text[header.end():end]
        events = {}; failed = False; successful = 0
        for line in part.splitlines():
            match = re.search(r"\[ew_event\] event_id=(\d+) stage=(\w+)",line)
            if match:
                identifier, stage = match.groups()
                if stage in {'decision','agent','tool','alert_output','complete'}:
                    events.setdefault(identifier,[]).append(stage)
                if stage == 'complete' and not re.search(r"\bresult=0(?:\s|$)",line): failed = True
        for identifier, stages in events.items():
            if int(identifier) > 0 and stages == ['decision','agent','tool','alert_output','complete'] and identifier not in seen_ids:
                successful += 1
            seen_ids.add(identifier)
        chains += successful
        snapshots = []
        for wire in re.findall(r"^\[ew-snapshot\] (.+)$",part,re.M):
            try:
                value = json.loads(wire)
                state = validate_snapshot(value,'stage3-'+str(index))
                sequence = state['snapshot_seq']; clock = state['updated_ms']
                if sequence <= previous_sequence or clock < previous_clock: continue
                previous_sequence, previous_clock = sequence, clock
                snapshots.append(state)
            except (ValueError, TypeError, GatewayError):
                continue
        checks['run_'+str(index)] = (successful >= 1 and not failed and bool(snapshots)
            and part.count('[ew-ctl] goto warn') >= 2
            and '[ew-ctl] goto chat' in part and '[ew-ctl] goto wifi' in part
            and '[ew-ctl] fake ' in part and '[alert_output] level=' in part)
    return {'software_chain':'PASS' if all(checks.values()) else 'FAIL',
            'checks':checks,'complete_event_chains':chains,'runs':runs,
            'physical_screen_buzzer_radar':'PENDING','board_tested':False,
            'note':'Serial logs prove software dispatch only; observe the board manually.'}


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
