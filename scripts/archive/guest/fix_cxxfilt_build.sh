#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela

echo "==== install cxxfilt $(date -Iseconds) ====" | tee -a "$LOG"
python3 -m pip install --user --break-system-packages cxxfilt >>"$LOG" 2>&1
python3 -c "import cxxfilt, elftools; print('deps_ok')" | tee -a "$LOG"

# smoke test mkallsyms with missing empty file (should still write empty table)
cd cmake_out/sf32lb52_devkit_lcd
python3 /home/a1/openvela/nuttx/tools/mkallsyms.py nuttx.empty allsyms_empty.c
echo "mk_exit=$?" | tee -a "$LOG"
head -5 allsyms_empty.c | tee -a "$LOG"

cd ~/openvela
echo "==== resume build $(date -Iseconds) ====" | tee -a "$LOG"
set +e
cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec=$?
echo "cmake_build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  # extract recent failures
  grep -E 'FAILED:|error:|Error|ModuleNotFound|Please execute' "$LOG" | tail -30 > /mnt/hgfs/VMware_share/artifacts/build_errors_tail.txt
  tail -40 "$LOG"
fi
exit $ec