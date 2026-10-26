#!/usr/bin/env python3
"""Use @scan/@join serial ctl (same process as UI) to avoid UART fight."""
import serial, time

sp = serial.Serial("COM7", 1_000_000, timeout=0.1)
sp.dtr = sp.rts = False

def go(cmd, recv=90):
    print(f"\n>>> {cmd}")
    sp.write(b"\r\n")
    time.sleep(0.2)
    while sp.in_waiting:
        sp.read(sp.in_waiting)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(0.5)
    end = time.time() + recv
    buf = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            buf += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    print(buf if buf.strip() else "(silent)")
    return buf

time.sleep(0.5)
go("@help", 5)
go("@ping", 15)
go("@status", 15)
go("@scan", 130)
sp.close()
