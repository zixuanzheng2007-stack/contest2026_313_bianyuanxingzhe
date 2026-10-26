#!/usr/bin/env python3
import serial, time

PORT, BAUD = "COM7", 1_000_000

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

sp = serial.Serial(PORT, BAUD, timeout=0.1)
sp.dtr = False
sp.rts = False
print("RESET via DTR...")
sp.dtr = True
time.sleep(0.15)
sp.dtr = False
print("listen 18s boot...")
boot = drain(sp, 18.0)
print("=== BOOT (last 1500 chars) ===")
print(boot[-1500:])
if "EW READY" not in boot and "nsh>" not in boot:
    print("WARN: no EW READY / nsh> in boot")

for cmd, recv in [
    ("ew at AT", 12),
    ("ew wifi scan", 130),
    ('ew wifi probe "Pura 80 Pro+"', 50),
    ("ew wifi", 15),
]:
    print(f"\n>>> {cmd}")
    sp.write(b"\r\n")
    time.sleep(0.3)
    drain(sp, 0.5)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(2.0)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)")

sp.close()
