#!/bin/bash
# Talk to NuttX NSH on USB-UART (/dev/ttyACM0), NOT Linux /dev/ttyS*
set -u
DEV=/dev/ttyACM0
OUT=/mnt/hgfs/VMware_share/artifacts/nsh_ttyS_probe.txt
LOG=/mnt/hgfs/VMware_share/artifacts/nsh_ttyS_probe.log
python3 - "$DEV" "$OUT" <<'PY'
import sys, time
dev, outpath = sys.argv[1], sys.argv[2]
try:
    import serial
except Exception as e:
    print("NO_PYSERIAL", e)
    raise SystemExit(2)
ser = serial.Serial(dev, 1000000, timeout=0.4)
ser.dtr = True
ser.rts = False
time.sleep(0.15)
ser.reset_input_buffer()
cmds = [
    b"\r\n",
    b"uname -a\r\n",
    b"ls /dev\r\n",
    b"ls /dev/tty*\r\n",
    b"help\r\n",
]
buf = b""
for c in cmds:
    ser.write(c)
    time.sleep(0.7)
    buf += ser.read(16384)
ser.close()
open(outpath, "wb").write(buf)
text = buf.decode("latin1", "replace")
print(text[:8000])
PY
echo "==== saved $OUT ====" | tee "$LOG"
