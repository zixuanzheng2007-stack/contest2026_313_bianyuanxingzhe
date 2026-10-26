#!/bin/bash
set -u
DEV=/dev/ttyACM0
OUT=/mnt/hgfs/VMware_share/artifacts/nsh_commands.txt
LOG=/mnt/hgfs/VMware_share/artifacts/nsh_smoke.log
python3 - "$DEV" "$OUT" <<'PY'
import time, sys
dev, outpath = sys.argv[1], sys.argv[2]
import serial
ser = serial.Serial(dev, 1000000, timeout=0.4)
ser.dtr = True
ser.rts = False
time.sleep(0.1)
ser.reset_input_buffer()
cmds = [b'\r\n', b'help\r\n', b'uname -a\r\n', b'free\r\n', b'ls /\r\n', b'i2c help\r\n']
buf = b''
for c in cmds:
    ser.write(c)
    time.sleep(0.6)
    chunk = ser.read(8192)
    buf += chunk
ser.close()
open(outpath, 'wb').write(buf)
text = buf.decode('latin1', 'replace')
print(text[:5000])
open(outpath.replace('.txt','_printable.txt'), 'w', encoding='utf-8', errors='replace').write(
    ''.join(ch if 32 <= ord(ch) < 127 or ch in '\r\n\t' else '.' for ch in text)
)
PY
echo "==== saved $OUT ====" | tee -a "$LOG"

# UART2 / pinmux hints
echo "==== UART2 pinmux search ====" | tee /mnt/hgfs/VMware_share/artifacts/uart2_pins.txt
BOARD=~/openvela/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd
rg -n -i 'UART2|USART2|pinmux|PA[0-9]+|PB[0-9]+' "$BOARD" --glob '*.{c,h,md,txt}' 2>/dev/null | head -80 | tee -a /mnt/hgfs/VMware_share/artifacts/uart2_pins.txt
rg -n -i 'UART2|USART2' ~/openvela/vendor/sifli -g '*devkit_lcd*' 2>/dev/null | head -40 | tee -a /mnt/hgfs/VMware_share/artifacts/uart2_pins.txt
ls "$BOARD" | tee -a /mnt/hgfs/VMware_share/artifacts/uart2_pins.txt