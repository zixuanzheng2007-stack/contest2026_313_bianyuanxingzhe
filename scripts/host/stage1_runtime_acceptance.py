#!/usr/bin/env python3
"""Stage-1 Wi-Fi/MiMo page-switch and Agent acceptance on the running UI."""

from __future__ import annotations

import argparse
import re
import time
from serial_common import artifact_path, open_port, receive, send_line, write_log


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--round-trips", type=int, default=20)
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = artifact_path("stage1_runtime_acceptance")
    transcript = [
        f"Stage-1 runtime acceptance {stamp}",
        f"port={args.port} baud=1000000 dtr=0 rts=0",
        f"round_trips={args.round_trips}",
    ]

    with open_port(args.port) as port:
        transcript.append(receive(port, 1.0))
        transcript.extend((">>> @status (before)", send_line(port, "@status", 24.0)))

        for index in range(args.round_trips):
            transcript.extend((f">>> round {index + 1} @goto wifi",
                               send_line(port, "@goto wifi", 7.0)))
            transcript.extend((f">>> round {index + 1} @goto chat",
                               send_line(port, "@goto chat", 2.0)))

        for index in range(3):
            transcript.extend((f">>> ask {index + 1}",
                               send_line(port, f"@ask 只回复阶段一成功{index + 1}", 65.0)))

        port.write("@ask 切页稳定性测试，只回复切页成功\r\n".encode("utf-8"))
        port.flush()
        transcript.append(">>> ask while switching")
        transcript.append(receive(port, 2.0))
        transcript.extend((">>> @goto wifi during ask",
                           send_line(port, "@goto wifi", 65.0)))
        transcript.extend((">>> @goto chat after ask",
                           send_line(port, "@goto chat", 3.0)))
        transcript.extend((">>> @status (after)", send_line(port, "@status", 24.0)))

    text = "\n".join(transcript)
    write_log(log_path, text)

    checks = {
        "no_unexpected_cwqap": "tx=AT+CWQAP" not in text,
        "all_agent_asks": text.count("[ew-ctl] ask ok:") >= 4,
        "associated": '+CWJAP:"' in text,
        "nonzero_ip": "+CIPSTA:ip:" in text and 'ip:"0.0.0.0"' not in text,
        "no_queue_drop": "queue full" not in text,
        "no_uart_error": re.search(
            r"(?:overrun|frame|noise)=[1-9][0-9]*", text) is None,
    }
    print(f"LOG={log_path}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    passed = all(checks.values())
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
