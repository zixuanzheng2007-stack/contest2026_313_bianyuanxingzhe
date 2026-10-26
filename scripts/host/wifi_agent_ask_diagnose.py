#!/usr/bin/env python3
"""Capture association before and after one Agent network request."""
from __future__ import annotations

import sys
import time
from serial_common import artifact_path, open_port, receive, send_line, write_log

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def send(sp: object, command: str, wait: float) -> str:
    print(f">>> {command}", flush=True)
    result = send_line(sp, command, wait)
    print(result[-7000:] if result else "(silent)", flush=True)
    return result


def main() -> int:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = artifact_path("wifi_agent_ask")
    sections = [
        f"Wi-Fi Agent ask diagnostic {stamp}",
        "port=COM7 baud=1000000 dtr=0 rts=0",
    ]
    with open_port("COM7") as sp:
        receive(sp, 1.0)
        for command, wait in (
            ("@status", 28.0),
            ("@goto chat", 3.0),
            ("@ask 测试当前网络", 60.0),
            ("@status", 28.0),
        ):
            result = send(sp, command, wait)
            sections.extend((f">>> {command}", result))

    text = "\n".join(sections)
    write_log(log_path, text)
    reset = "tx=AT+RST" in text
    disconnected = 'ip:"0.0.0.0"' in text or "WIFI DISCONNECT" in text
    ask_ok = "[ew-ctl] ask ok:" in text
    print(f"LOG={log_path}")
    print(f"ASK={'PASS' if ask_ok else 'FAIL'} RESET={int(reset)} DISCONNECTED={int(disconnected)}")
    return 0 if ask_ok and not reset and not disconnected else 1


if __name__ == "__main__":
    raise SystemExit(main())
