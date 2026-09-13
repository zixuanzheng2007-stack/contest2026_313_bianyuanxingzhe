#!/usr/bin/env python3
"""NSH：外挂 ESP AT 猫连通性。控制台 1Mbps，必须 rts=False。"""
from __future__ import annotations

import argparse
import sys
import time

import serial


def nsh_session(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial(port, baudrate=baud, timeout=0.2)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.15)
    ser.reset_input_buffer()
    ser.write(b"\r")
    time.sleep(0.2)
    ser.reset_input_buffer()
    return ser


def run_cmd(ser: serial.Serial, cmd: str, wait: float) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\r").encode("ascii", errors="replace"))
    ser.flush()
    deadline = time.time() + wait
    chunks: list[bytes] = []
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            chunks.append(ser.read(n))
        else:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port", default="/dev/ttyACM0")
    ap.add_argument("-b", "--baud", type=int, default=1000000)
    ap.add_argument(
        "--smart",
        action="store_true",
        help="ew wifi：无 SSID 时启动 ESP-Touch（约 40s，用乐鑫 Esptouch 配网）",
    )
    args = ap.parse_args()

    try:
        ser = nsh_session(args.port, args.baud)
    except Exception as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("把 CH343 透传到这台虚拟机后再测（RTS 必须拉低）。", file=sys.stderr)
        return 1

    print("==> ew wifi ping")
    print(run_cmd(ser, "ew wifi ping", 3.0))
    print("==> ew at AT+GMR")
    print(run_cmd(ser, "ew at AT+GMR", 3.0))
    if args.smart:
        print("==> ew wifi  (SmartConfig，请用手机 Esptouch)")
        print(run_cmd(ser, "ew wifi", 50.0))
    print("==> ew wifi status")
    print(run_cmd(ser, "ew wifi status", 8.0))
    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
