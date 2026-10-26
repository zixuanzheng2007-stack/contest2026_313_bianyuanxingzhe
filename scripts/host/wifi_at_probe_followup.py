#!/usr/bin/env python3
import serial, time, sys

PORT, BAUD = "COM7", 1_000_000

def drain(sp, sec):
    end = time.time() + sec
    b = ""
    while time.time() < end:
        n = sp.in_waiting
        if n: b += sp.read(n).decode("utf-8", "replace")
        else: time.sleep(0.05)
    return b

def run(sp, cmd, recv):
    print(f"\n>>> {cmd}", flush=True)
    sp.write(b"\r\n"); time.sleep(0.2); drain(sp, 0.2)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.5)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out

sp = serial.Serial(PORT, BAUD, timeout=0.1)
sp.dtr = sp.rts = False
drain(sp, 1)

cmds = [
    ("ew at AT", 15),
    ('ew wifi probe "Pura 80 Pro+"', 60),
    ("ew wifi", 20),
    ("ew wifi join", 45),
]
all_out = ""
for c, r in cmds:
    all_out += run(sp, c, r)
sp.close()

print("\n--- counts ---")
print("raw +CWLAP:", all_out.count("+CWLAP:"))
print("markers in fw log:", all_out.count("markers="))
sys.exit(0)
