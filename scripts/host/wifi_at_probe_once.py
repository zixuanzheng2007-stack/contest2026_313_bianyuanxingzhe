#!/usr/bin/env python3
"""Interactive NSH probe: reset, wait boot, run key WiFi commands one-by-one."""
from __future__ import annotations

import re
import sys
import time

import serial

PORT = "COM7"
BAUD = 1_000_000


def drain(sp: serial.Serial, sec: float) -> str:
    end = time.time() + sec
    buf = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            buf += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return buf


def wait_prompt(sp: serial.Serial, timeout: float = 30.0) -> str:
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            chunk = sp.read(n).decode("utf-8", "replace")
            buf += chunk
            if "nsh>" in buf or "EW READY" in buf:
                return buf
        else:
            time.sleep(0.05)
    return buf


def run_cmd(sp: serial.Serial, cmd: str, recv_sec: float) -> str:
    print(f"\n{'='*60}\n>>> {cmd}\n{'='*60}", flush=True)
    sp.write(b"\x03")  # break any hung command
    time.sleep(0.4)
    drain(sp, 0.5)
    sp.write(b"\r\n")
    time.sleep(0.25)
    drain(sp, 0.3)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv_sec)
    # keep reading if CWLAP/scan still streaming
    if "+CWLAP:" in out and "OK" not in out:
        out += drain(sp, min(recv_sec, 30.0))
    print(out if out.strip() else "(silent)", flush=True)
    return out


def main() -> int:
    sp = serial.Serial(PORT, BAUD, timeout=0.1)
    sp.dtr = False
    sp.rts = False

    print("DTR reset pulse...", flush=True)
    sp.dtr = True
    time.sleep(0.12)
    sp.dtr = False

    print("Waiting boot (20s)...", flush=True)
    boot = wait_prompt(sp, 25.0)
    boot += drain(sp, 2.0)
    print("--- BOOT TAIL ---")
    print(boot[-1200:] if len(boot) > 1200 else boot)

    steps = [
        ("ew at AT", 12.0),
        ("ew at AT+CWMODE?", 12.0),
        ("ew at AT+CWLAP", 70.0),
        ("ew wifi scan", 130.0),
        ('ew wifi probe "Pura 80 Pro+"', 35.0),
        ("ew wifi ping", 25.0),
        ("ew wifi", 15.0),
        ("ew at AT+CIPSTA?", 12.0),
    ]

    all_out = boot
    for cmd, recv in steps:
        all_out += run_cmd(sp, cmd, recv)

    sp.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    markers = all_out.count("+CWLAP:")
    print(f"CWLAP markers in log: {markers}")
    if "wake ok" in all_out or "rx=OK" in all_out or "MODEM: OK" in all_out:
        print("MODEM: OK")
    elif "no reply" in all_out or "not responding" in all_out:
        print("MODEM: FAIL")
    else:
        print("MODEM: unclear")

    m = re.search(r"(\d+) network\(s\)", all_out)
    if m:
        print(f"ew wifi scan parsed: {m.group(1)} networks")
    if markers > 0 and m and int(m.group(1)) == 0:
        print(">>> PARSER ISSUE: raw CWLAP has data but scan list empty")
    if "probe hit" in all_out:
        print("PROBE: hit Pura 80 Pro+")
    elif "probe miss" in all_out:
        print("PROBE: miss (ESP did not see hotspot)")
    if "Network: ONLINE" in all_out or "WIFI ON" in all_out:
        print("NETWORK: ONLINE")
    elif "LAN ONLY" in all_out or "WIFI LAN" in all_out:
        print("NETWORK: LAN only")
    elif "WIFI: connected" in all_out:
        print("NETWORK: WiFi linked, no IP/internet yet")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
