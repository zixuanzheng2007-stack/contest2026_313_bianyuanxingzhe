#!/bin/bash
set -u
export PATH="$HOME/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
BOARD=vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd

echo "==== BUILD START $(date -Iseconds) ====" | tee "$LOG"
# show usage
./build.sh -h 2>&1 | head -40 | tee -a "$LOG" || true
grep -n "build_board\|Usage\|usage\|BOARD" build.sh | head -30 | tee -a "$LOG"

# Prefer documented form
set +e
if ./build.sh "$BOARD" >>"$LOG" 2>&1; then
  ec=0
else
  ec=$?
  echo "first_try_exit=$ec" | tee -a "$LOG"
  # alternate forms
  ./build.sh -b "$BOARD" >>"$LOG" 2>&1
  ec=$?
fi
set -e
echo "build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"

find . -name nuttx.bin 2>/dev/null | head -10 | tee -a "$LOG"
BIN=$(find . -name nuttx.bin 2>/dev/null | head -1)
if [ -n "$BIN" ]; then
  cp -f "$BIN" /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la /mnt/hgfs/VMware_share/artifacts/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  echo NO_BIN | tee -a "$LOG"
fi