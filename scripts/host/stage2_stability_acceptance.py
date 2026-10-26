#!/usr/bin/env python3
"""Long-running UI, Wi-Fi association, queue, and UART stability check."""

from __future__ import annotations

import argparse
import re
import time

from serial_common import artifact_path, open_port, receive, send_line, write_log


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--minutes", type=float, default=30.0)
    args = parser.parse_args()
    duration = max(60.0, args.minutes * 60.0)
    log_path = artifact_path("stage2_stability")
    transcript = [
        "Stage-2 stability acceptance",
        f"port={args.port} baud=1000000 dtr=0 rts=0 duration_s={duration:.0f}",
    ]
    help_results: list[str] = []
    status_results: list[str] = []

    with open_port(args.port) as port:
        transcript.append(receive(port, 1.0))
        start = time.monotonic()
        next_help = start
        next_status = start
        while time.monotonic() - start < duration:
            now = time.monotonic()
            elapsed = now - start
            if now >= next_status:
                result = send_line(port, "@status", 28.0)
                status_results.append(result)
                transcript.extend((f">>> t={elapsed:.1f}s @status", result))
                next_status += 300.0
            elif now >= next_help:
                result = send_line(port, "@help", 2.0)
                help_results.append(result)
                transcript.extend((f">>> t={elapsed:.1f}s @help", result))
                next_help += 30.0
            else:
                transcript.append(receive(port, min(1.0, next_help - now,
                                                     next_status - now)))

        result = send_line(port, "@status", 28.0)
        status_results.append(result)
        transcript.extend((">>> final @status", result))

    text = "\n".join(transcript)
    write_log(log_path, text)
    responsive = sum("[ew-ctl] cmd: help" in result for result in help_results)
    associated = all('+CWJAP:"' in result for result in status_results)
    nonzero_ip = all(
        re.search(r'\+CIPSTA:ip:"(?!0\.0\.0\.0)[^"]+"', result) is not None
        for result in status_results
    )
    checks = {
        "runtime responsive": responsive == len(help_results) and responsive > 0,
        "Wi-Fi stayed associated": associated and len(status_results) >= 2,
        "IP stayed nonzero": nonzero_ip,
        "no unexpected disconnect": "WIFI DISCONNECT" not in text,
        "no queue overflow": "queue full" not in text,
        "no UART error": re.search(
            r"(?:overrun|frame|noise)=[1-9][0-9]*", text) is None,
        "no process-failure marker": not re.search(
            r"(?:assert|panic|segmentation fault|HardFault)", text,
            re.IGNORECASE),
    }
    print(f"LOG={log_path}")
    print(f"HELP_RESPONSES={responsive}/{len(help_results)} STATUS_CHECKS={len(status_results)}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    passed = all(checks.values())
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
