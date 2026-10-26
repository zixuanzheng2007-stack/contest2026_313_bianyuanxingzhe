#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
LOG=/mnt/hgfs/VMware_share/artifacts/flash_uart2.log
BIN=/mnt/hgfs/VMware_share/artifacts/nuttx.bin
BAUD="${1:-115200}"
COMPAT="${2:-true}"
echo "==== FLASH $(date '+%Y-%m-%dT%H:%M:%S') baud=$BAUD compat=$COMPAT ====" | tee "$LOG"
fuser -k /dev/ttyACM0 2>/dev/null || true
sleep 1
python3 - <<'PY'
import serial, time
try:
    s = serial.Serial('/dev/ttyACM0', 1000000, timeout=0.2)
    s.dtr = False
    s.rts = True
    time.sleep(0.1)
    s.dtr = True
    s.rts = False
    time.sleep(0.2)
    s.close()
    print('reset_pulse_ok')
except Exception as e:
    print('reset_pulse_skip', e)
PY
sftool -c SF32LB52 -p /dev/ttyACM0 -b "$BAUD" --compat "$COMPAT" --connect-attempts 8 \
  write_flash --verify "$BIN@0x12010000" 2>&1 | tee -a "$LOG"
echo "flash_exit=${PIPESTATUS[0]}" | tee -a "$LOG"
