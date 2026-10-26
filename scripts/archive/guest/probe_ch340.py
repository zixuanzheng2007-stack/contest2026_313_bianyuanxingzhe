import time
from serial import Serial
from serial.tools import list_ports

print("=== ports ===")
for p in list_ports.comports():
    print(f"{p.device} {p.description}")

port = "COM5"
baud = 115200
print(f"=== read {port} {baud} 2.0s ===")
ser = Serial(port, baud, timeout=0.2)
ser.dtr = True
ser.rts = False
time.sleep(0.1)
ser.reset_input_buffer()
t0 = time.time()
buf = bytearray()
while time.time() - t0 < 2.0:
    chunk = ser.read(256)
    if chunk:
        buf.extend(chunk)
ser.close()
print(f"bytes={len(buf)}")
if buf:
    print("head:", buf[:64].hex(" "))
    print("ascii:", "".join(chr(b) if 32 <= b < 127 else "." for b in buf[:64]))
    sig = bytes.fromhex("f4f3f2f1")
    print("has_F4F3F2F1", sig in buf)
else:
    print("no_uart_data")
