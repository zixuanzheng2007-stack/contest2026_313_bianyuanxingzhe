#!/usr/bin/env python3
"""Verify that remote keyboard input does not force Wi-Fi to Agent."""
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
            time.sleep(0.02)
    return "".join(parts)


def send(sp: serial.Serial, command: str, wait: float) -> str:
    shown = "@input <redacted>" if command.startswith("@input ") else command
    print(f">>> {shown}", flush=True)
    sp.write((command + "\r\n").encode("utf-8"))
    sp.flush()
    text = receive(sp, wait)
    print(text[-4000:] if text else "(silent)", flush=True)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="wait for scan, open first secured AP, and test scroll")
    args = ap.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = ARTIFACTS / f"pc_input_routing_{stamp}.txt"
    with serial.Serial("COM7", 1_000_000, timeout=0.02) as sp:
        sp.dtr = False
        sp.rts = False
        receive(sp, 1.0)
        goto_text = send(sp, "@goto wifi", 135.0 if args.full else 3.0)
        setup_text = ""
        if args.full:
            setup_text += send(sp, "@tap 195 154", 3.0)
        input_text = send(sp, "@input 12345678", 4.0)
        if args.full:
            setup_text += send(sp, "@key escape", 2.0)
            setup_text += send(sp, "@touch down 195 250", 0.3)
            setup_text += send(sp, "@touch move 195 190", 0.3)
            setup_text += send(sp, "@touch up 195 190", 2.0)
        tail = receive(sp, 3.0)

    text = (
        f"PC input routing {stamp}\nport=COM7 baud=1000000 dtr=0 rts=0\n"
        f">>> @goto wifi\n{goto_text}\n"
        f">>> setup/scroll\n{setup_text}\n"
        f">>> @input <redacted>\n{input_text}\n{tail}"
    )
    log_path.write_text(text, encoding="utf-8")
    jumped = "[ew-ui] page=1" in input_text + setup_text + tail
    stayed_wifi = "[ew-ui] page=2" in goto_text
    input_ok = "input ok bytes=8" in input_text
    print(f"LOG={log_path}")
    passed = stayed_wifi and not jumped and (input_ok if args.full else True)
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
