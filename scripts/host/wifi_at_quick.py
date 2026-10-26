#!/usr/bin/env python3
import serial, time

sp = serial.Serial("COM7", 1_000_000, timeout=0.1)
sp.dtr = sp.rts = False

def go(cmd, recv=12):
    print(f"\n>>> {cmd}")
    sp.write(b"\r\n")
    time.sleep(0.25)
    while sp.in_waiting:
        sp.read(sp.in_waiting)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.0)
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

drain = go("help", 3)
go("ew help", 5)
go("ew at AT", 15)
go("ew wifi scan", 130)
go("ew wifi probe Pura", 45)
go('ew wifi join "Pura 80 Pro+"', 50)
sp.close()
