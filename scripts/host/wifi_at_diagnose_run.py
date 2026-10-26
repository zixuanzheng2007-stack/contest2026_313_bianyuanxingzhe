#!/usr/bin/env python3
"""GPT 方案 §23：只跑 AT 层诊断，不碰 ew ask。"""
import serial
import time
from pathlib import Path

PORT, BAUD = "COM7", 1_000_000
ART = Path(__file__).resolve().parents[2] / "VMware_share" / "artifacts"
STEPS = [
    ("@ping", 12.0),  # 先唤醒 modem，避免 NSH 抢 @
    ("ew at AT", 15.0),
    ("ew at AT+GMR", 8.0),
    ("ew at AT+CWMODE?", 8.0),
    ("ew at AT+CWSTATE?", 8.0),
    ("ew at AT+CWLAP", 70.0),
    ("@scan", 130.0),
    ("ew wifi ping", 30.0),
]


def drain(sp, sec):
    end = time.time() + sec
    b = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            b += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return b


def nsh(sp, cmd, recv):
    print(f"\n{'='*60}\n>>> {cmd}\n{'='*60}", flush=True)
    sp.write(b"\r\n")
    time.sleep(0.35)
    drain(sp, 0.4)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.2)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def at_cmd(sp, cmd, recv):
    print(f"\n{'='*60}\n>>> {cmd}\n{'='*60}", flush=True)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def main():
    sp = serial.Serial(PORT, BAUD, timeout=0.1)
    sp.dtr = sp.rts = False
    # soft reset, wait boot
    sp.dtr = True
    time.sleep(0.15)
    sp.dtr = False
    print("boot wait 22s...", flush=True)
    boot = drain(sp, 22.0)
    all_out = boot
    time.sleep(3.0)

    for cmd, recv in STEPS:
        if cmd.startswith("@"):
            all_out += at_cmd(sp, cmd, recv)
        else:
            all_out += nsh(sp, cmd, recv)

    sp.close()
    log = ART / f"wifi_gpt_diagnose_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log.write_text(all_out, encoding="utf-8")
    print(f"\nLOG: {log}", flush=True)


if __name__ == "__main__":
    main()
