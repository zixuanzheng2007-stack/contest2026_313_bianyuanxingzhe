#!/bin/bash
set -u
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd /home/a1/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/build_uart2.log
echo "==== BUILD UART2 $(date -Iseconds) ====" | tee "$LOG"
# confirm patch present
grep -n "115200\|ttyS1\|UART2_INDEX" vendor/sifli/chips/sf32lb52/sifli_uart.c | tee -a "$LOG"
cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec=$?
echo "build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG"
fi
exit $ec
