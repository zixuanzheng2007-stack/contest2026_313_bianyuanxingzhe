#!/bin/bash
python3 - <<'PY'
import time, serial
ser = serial.Serial("/dev/ttyACM0", 1000000, timeout=0.5)
ser.dtr = True
ser.rts = False
time.sleep(0.15)
ser.reset_input_buffer()
for c in [b"\r\n", b"dmesg\r\n", b"hexdump /dev/ttyS1\r\n", b"cat /dev/ttyS1\r\n"]:
    ser.write(c)
    time.sleep(1.2)
data = ser.read(32768)
ser.close()
text = data.decode("latin1", "replace")
open("/mnt/hgfs/VMware_share/artifacts/nsh_dmesg_uart.txt","w",encoding="utf-8",errors="replace").write(text)
print(text[-6000:])
PY
