#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/nsh_smoke.log
OUT=/mnt/hgfs/VMware_share/artifacts/nsh_console_capture.txt
DEV=/dev/ttyACM0
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== NSH smoke $(date -Iseconds) ====" | tee "$LOG"

if [ ! -e "$DEV" ]; then
  echo "NO_DEVICE $DEV" | tee -a "$LOG"
  exit 2
fi

# free port if held
fuser -k "$DEV" 2>/dev/null || true
sleep 1

try_baud() {
  local baud="$1"
  local cap="/tmp/nsh_cap_${baud}.txt"
  echo "---- baud=$baud ----" | tee -a "$LOG"
  python3 - "$DEV" "$baud" "$cap" <<'PY'
import sys, time
dev, baud, outpath = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    import serial
except ImportError:
    # fallback: termios raw read
    import os, termios, tty, select
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    tty.setraw(fd)
    # map common bauds
    baudmap = {
        115200: termios.B115200,
        1000000: getattr(termios, 'B1000000', termios.B115200),
    }
    speed = baudmap.get(baud, termios.B115200)
    attrs[4] = speed
    attrs[5] = speed
    attrs[2] = attrs[2] | termios.CREAD | termios.CLOCAL
    # 8N1
    attrs[2] &= ~termios.CSIZE
    attrs[2] |= termios.CS8
    attrs[2] &= ~(termios.PARENB | termios.CSTOPB)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    # pulse DTR for possible reset
    try:
        import fcntl, struct
        TIOCMGET = 0x5415
        TIOCMSET = 0x5418
        TIOCM_DTR = 0x002
        TIOCM_RTS = 0x004
        buf = fcntl.ioctl(fd, TIOCMGET, struct.pack('I', 0))
        flags = struct.unpack('I', buf)[0]
        fcntl.ioctl(fd, TIOCMSET, struct.pack('I', flags & ~TIOCM_DTR & ~TIOCM_RTS))
        time.sleep(0.1)
        fcntl.ioctl(fd, TIOCMSET, struct.pack('I', flags | TIOCM_DTR))
    except Exception:
        pass
    data = b''
    end = time.time() + 10
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 4096)
                if chunk:
                    data += chunk
            except BlockingIOError:
                pass
    os.close(fd)
    open(outpath, 'wb').write(data)
    sys.stdout.buffer.write(data[:4000])
    sys.exit(0 if data else 3)

# pyserial path
ser = serial.Serial()
ser.port = dev
ser.baudrate = baud
ser.bytesize = serial.EIGHTBITS
ser.parity = serial.PARITY_NONE
ser.stopbits = serial.STOPBITS_ONE
ser.timeout = 0.2
ser.dsrdtr = False
ser.rtscts = False
ser.open()
# pulse DTR
try:
    ser.dtr = False
    ser.rts = False
    time.sleep(0.05)
    ser.dtr = True
except Exception:
    pass
time.sleep(0.2)
ser.reset_input_buffer()
# send CR to wake nsh if already up
try:
    ser.write(b'\r\n')
except Exception:
    pass
data = b''
end = time.time() + 10
while time.time() < end:
    chunk = ser.read(4096)
    if chunk:
        data += chunk
ser.close()
open(outpath, 'wb').write(data)
sys.stdout.buffer.write(data[:4000])
sys.exit(0 if data else 3)
PY
  local ec=$?
  echo "capture_exit=$ec bytes=$(wc -c < "$cap" 2>/dev/null || echo 0)" | tee -a "$LOG"
  if [ -s "$cap" ]; then
    # save text-ish
    cat "$cap" | tr -cd '\11\12\15\40-\176' > "${cap}.txt"
    echo "---- printable preview ----" | tee -a "$LOG"
    head -c 2000 "${cap}.txt" | tee -a "$LOG"
    echo | tee -a "$LOG"
    if grep -aEiq 'nsh>|NuttShell|NuttX|SF32|openvela|siFli|SiFli|applet' "$cap"; then
      echo "PASS_KEYWORDS baud=$baud" | tee -a "$LOG"
      cp -f "$cap" "$OUT"
      cp -f "${cap}.txt" /mnt/hgfs/VMware_share/artifacts/nsh_console_printable.txt
      return 0
    fi
    echo "DATA_NO_KEYWORD baud=$baud" | tee -a "$LOG"
    cp -f "$cap" "$OUT"
    cp -f "${cap}.txt" /mnt/hgfs/VMware_share/artifacts/nsh_console_printable.txt
    return 1
  fi
  return 2
}

ok=1
try_baud 1000000 && ok=0
if [ $ok -ne 0 ]; then
  try_baud 115200 && ok=0
fi

# also try sending help if we got a quiet but open port
if [ $ok -ne 0 ]; then
  echo "---- interactive probe 1000000 ----" | tee -a "$LOG"
  python3 - <<'PY' | tee -a "$LOG"
import time
try:
  import serial
except Exception as e:
  print('no pyserial', e); raise SystemExit(0)
ser=serial.Serial('/dev/ttyACM0', 1000000, timeout=0.3)
ser.dtr=True; ser.rts=False
time.sleep(0.1)
for cmd in [b'\r\n', b'help\r\n', b'uname -a\r\n', b'free\r\n']:
  ser.write(cmd)
  time.sleep(0.5)
  print(ser.read(4096).decode('latin1','replace'))
ser.close()
PY
fi

if grep -q 'PASS_KEYWORDS' "$LOG"; then
  echo NSH_SMOKE_PASS | tee /mnt/hgfs/VMware_share/artifacts/NSH_SMOKE_PASS.txt
  exit 0
fi
echo NSH_SMOKE_NEED_RESET | tee /mnt/hgfs/VMware_share/artifacts/NSH_SMOKE_NEED_RESET.txt
exit 3