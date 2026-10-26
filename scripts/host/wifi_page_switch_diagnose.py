#!/usr/bin/env python3
"""Capture Wi-Fi association across UI page switches."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "VMware_share" / "artifacts"


def receive(sp: serial.Serial, seconds: float) -> str:
    deadline = time.monotonic() + seconds
    parts: list[str] = []
    while time.monotonic() < deadline:
        if sp.in_waiting:
            parts.append(sp.read(sp.in_waiting).decode("utf-8", "replace"))
        else:
            time.sleep(0.03)
    return "".join(parts)


def send(sp: serial.Serial, command: str, wait: float) -> str:
    print(f">>> {command}", flush=True)
    sp.write((command + "\r\n").encode("utf-8"))
    sp.flush()
    result = receive(sp, wait)
    print(result[-5000:] if result else "(silent)", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--touch", action="store_true",
                    help="switch pages through the same touch path as the PC panel")
    args = ap.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = ARTIFACTS / f"wifi_page_switch_{stamp}.txt"
    sections: list[str] = [
        f"Wi-Fi page switch diagnostic {stamp}",
        "port=COM7 baud=1000000 dtr=0 rts=0",
    ]
    with serial.Serial("COM7", 1_000_000, timeout=0.02) as sp:
        sp.dtr = False
        sp.rts = False
        receive(sp, 1.0)
        if args.touch:
            steps = (
                ("@goto wifi", 135.0),
                ("@status", 28.0),
                ("@tap 60 35", 3.0),
                ("@status", 28.0),
                ("@tap 340 35", 3.0),
                ("@status", 28.0),
            )
        else:
            steps = (
                ("@status", 28.0),
                ("@goto warn", 3.0),
                ("@status", 28.0),
                ("@goto chat", 3.0),
                ("@status", 28.0),
                ("@goto wifi", 135.0),
                ("@status", 28.0),
            )
        for command, wait in steps:
            result = send(sp, command, wait)
            sections.extend((f">>> {command}", result))

    text = "\n".join(sections)
    log_path.write_text(text, encoding="utf-8")
    disconnects = text.count("tx=AT+CWQAP")
    joined = text.count('+CWJAP:"')
    zero_ip = text.count('ip:"0.0.0.0"')
    print(f"LOG={log_path}")
    print(f"CWQAP_COUNT={disconnects} JOINED_SNAPSHOTS={joined} ZERO_IP={zero_ip}")
    print(f"VERDICT={'PASS' if disconnects == 0 and zero_ip == 0 else 'FAIL'}")
    return 0 if disconnects == 0 and zero_ip == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
