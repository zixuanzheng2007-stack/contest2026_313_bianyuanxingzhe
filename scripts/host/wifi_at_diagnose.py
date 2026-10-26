#!/usr/bin/env python3
"""One-shot ESP-AT WiFi layered diagnose over NSH (COM7 @ 1Mbps)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    raise

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "VMware_share" / "artifacts"


def recv(sp: serial.Serial, sec: float) -> str:
    end = time.time() + sec
    buf = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            buf += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return buf


def cmd(sp: serial.Serial, line: str, wait: float, recv_sec: float, log: list[str]) -> str:
    log.append("")
    log.append(f">>> {line}")
    print(f"\n>>> {line}", flush=True)
    sp.write(b"\r\n")
    time.sleep(0.2)
    sp.write(f"{line}\r\n".encode())
    time.sleep(wait)
    out = recv(sp, recv_sec)
    text = out if out.strip() else "(no output)"
    log.append(text)
    print(text, flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM7")
    ap.add_argument("--baud", type=int, default=1_000_000)
    ap.add_argument("--boot-wait", type=float, default=8.0)
    ap.add_argument("--probe-ssid", default="Pura 80 Pro+")
    args = ap.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    log_path = ARTIFACTS / f"wifi_at_diagnose_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log: list[str] = []

    def note(s: str) -> None:
        log.append(s)
        print(s, flush=True)

    note(f"=== WiFi AT diagnose === Port={args.port} Baud={args.baud}")

    sp = serial.Serial(args.port, args.baud, timeout=0.1)
    sp.dtr = False
    sp.rts = False

    recv(sp, 1.5)
    note(f"--- boot wait {args.boot_wait}s ---")
    time.sleep(args.boot_wait)
    recv(sp, 2.0)

    all_out = ""
    steps: list[tuple[str, float, float]] = [
        ("ew wifi ping", 2.0, 8.0),
        ("ew at AT", 1.0, 4.0),
        ("ew at AT+GMR", 1.0, 5.0),
        ("ew at AT+CWMODE?", 1.0, 4.0),
        ("ew at AT+CWLAP", 3.0, 55.0),
        ("ew wifi scan", 2.0, 90.0),
    ]
    if args.probe_ssid:
        q = args.probe_ssid.replace('"', '\\"')
        steps.append((f'ew wifi probe "{q}"', 2.0, 25.0))
    steps.extend([
        ("ew wifi raw", 2.0, 12.0),
        ("ew at AT+CIPSTA?", 1.0, 5.0),
        ("ew wifi", 2.0, 8.0),
    ])

    for line, wait, recv_sec in steps:
        all_out += cmd(sp, line, wait, recv_sec, log)

    sp.close()
    log_path.write_text("\n".join(log), encoding="utf-8")
    note(f"\nLog saved: {log_path}")

    # Quick verdict
    note("\n=== VERDICT ===")
    if "MODEM: not responding" in all_out or "no reply" in all_out.lower():
        if "rx=OK" not in all_out and "OK" not in all_out.split("ew at AT")[-1][:200]:
            note("FAIL: UART/AT silent or unstable — check wiring, ESP-AT firmware, baud")
    elif "+CWLAP:" in all_out and "ew wifi scan" in all_out:
        raw_markers = all_out.count("+CWLAP:")
        if "network(s)" in all_out:
            import re
            m = re.search(r"(\d+) network\(s\)", all_out)
            scan_n = int(m.group(1)) if m else -1
            if raw_markers > 0 and scan_n == 0:
                note(f"SUSPECT PARSER: raw CWLAP markers~{raw_markers} but scan list empty")
            elif scan_n >= 0:
                note(f"SCAN: {scan_n} network(s) parsed from modem")
    if "Network: ONLINE" in all_out or "WIFI ON" in all_out:
        note("PASS: online")
    elif "LAN: ip=" in all_out or "WIFI LAN" in all_out:
        note("PARTIAL: LAN only (WiFi+IP ok, internet probe failed)")
    elif "WIFI: connected" in all_out or "WIFI CONNECTED" in all_out:
        note("PARTIAL: WiFi associated, check DHCP/IP")
    elif "MODEM: OK" in all_out or "wake ok" in all_out:
        note("PARTIAL: modem OK, WiFi not connected — scan/join next")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
