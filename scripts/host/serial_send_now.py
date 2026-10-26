#!/usr/bin/env python3
"""Send serial commands to COM7 (1Mbps)."""
import sys
import time
import serial

PORT, BAUD = "COM7", 1_000_000
CMDS = [
    ("@ping", 18.0),
    ("@status", 35.0),
    ("ew wifi ping", 28.0),
    ("ew wifi", 12.0),
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


def send_at(sp, cmd, recv):
    print(f"\n>>> {cmd}", flush=True)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def send_nsh(sp, cmd, recv):
    print(f"\n>>> {cmd}", flush=True)
    sp.write(b"\r\n")
    time.sleep(0.4)
    drain(sp, 0.4)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.5)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def main():
    sp = serial.Serial(PORT, BAUD, timeout=0.1)
    sp.dtr = sp.rts = False
    drain(sp, 0.5)
    for cmd, recv in CMDS:
        if cmd.startswith("@"):
            send_at(sp, cmd, recv)
        else:
            send_nsh(sp, cmd, recv)
    sp.close()


if __name__ == "__main__":
    main()
