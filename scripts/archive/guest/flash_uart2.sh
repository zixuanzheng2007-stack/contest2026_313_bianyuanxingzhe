#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
LOG=/mnt/hgfs/VMware_share/artifacts/flash_uart2.log
BIN=/mnt/hgfs/VMware_share/artifacts/nuttx.bin
echo "==== FLASH $(date -Iseconds) ====" | tee "$LOG"
fuser -k /dev/ttyACM0 2>/dev/null || true
sleep 1
sftool -c SF32LB52 -p /dev/ttyACM0 -b 1000000 write_flash --verify "$BIN@0x12010000" 2>&1 | tee -a "$LOG"
echo "flash_exit=${PIPESTATUS[0]}" | tee -a "$LOG"
sleep 2
python3 - <<'PY'
import time, serial
ser = serial.Serial("/dev/ttyACM0", 1000000, timeout=0.4)
ser.dtr = True
ser.rts = False
time.sleep(0.2)
ser.reset_input_buffer()
ser.write(b"\r\nls /dev\r\nuname -a\r\n")
time.sleep(1.2)
data = ser.read(8192)
ser.close()
open("/mnt/hgfs/VMware_share/artifacts/nsh_after_flash.txt","wb").write(data)
print(data.decode("latin1","replace"))
PY
