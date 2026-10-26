#!/usr/bin/env python3
"""TASK_031 post-flash acceptance: WiFi page scan + status (no password)."""
from __future__ import annotations

import time
from pathlib import Path

import serial

ART = Path(__file__).resolve().parents[2] / "VMware_share" / "artifacts"
PORT, BAUD = "COM7", 1_000_000


def drain(sp: serial.Serial, sec: float) -> str:
    end = time.time() + sec
    buf = ""
    while time.time() < end:
        if sp.in_waiting:
            buf += sp.read(sp.in_waiting).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return buf


def at_cmd(sp: serial.Serial, cmd: str, recv: float) -> str:
    print(f">>> @{cmd}", flush=True)
    sp.write(f"@{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv)
    print(out[-2000:] if len(out) > 2000 else (out or "(silent)"), flush=True)
    return out


def main() -> None:
    sp = serial.Serial(PORT, BAUD, timeout=0.1)
    sp.dtr = sp.rts = False
    print("wait boot 18s...", flush=True)
    all_out = drain(sp, 18)
    if "EW READY" not in all_out:
        sp.rts = True
        time.sleep(0.12)
        sp.rts = False
        all_out += drain(sp, 20)

    all_out += at_cmd(sp, "goto wifi", 8)
    time.sleep(3)
    all_out += at_cmd(sp, "scan", 130)
    all_out += at_cmd(sp, "status", 20)
    all_out += at_cmd(sp, "ping", 15)
    sp.close()

    log = ART / f"task031_accept_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log.write_text(all_out, encoding="utf-8")
    print(f"\nLog: {log}")
    print("--- summary ---")
    print("EW READY:", "EW READY" in all_out)
    ap_hits = all_out.count("+CWLAP:") + all_out.lower().count("rssi")
    print("scan hints:", ap_hits)
    print("ONLINE:", "ONLINE" in all_out)
    print("LAN ONLY:", "LAN ONLY" in all_out)


if __name__ == "__main__":
    main()
