import time
import serial

ser = serial.Serial("/dev/ttyACM0", 1000000, timeout=0.5)
ser.dtr = True
ser.rts = False
time.sleep(0.15)
ser.reset_input_buffer()
buf = b""
for c in [b"\r\n", b"dmesg\r\n"]:
    ser.write(c)
    time.sleep(1.6)
    buf += ser.read(32768)
ser.close()
open("/mnt/hgfs/VMware_share/artifacts/nsh_dmesg_uart.txt", "wb").write(buf)
print(buf.decode("latin1", "replace")[-5000:])
