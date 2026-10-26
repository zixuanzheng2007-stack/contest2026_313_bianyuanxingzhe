#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela

echo "==== fix mkallsyms $(date -Iseconds) ====" | tee -a "$LOG"
python3 -m pip install --user --break-system-packages pyelftools >>"$LOG" 2>&1
python3 -c "import elftools; print('pyelftools_ok')" | tee -a "$LOG"

# reproduce error
cd cmake_out/sf32lb52_devkit_lcd
set +e
python3 /home/a1/openvela/nuttx/tools/mkallsyms.py nuttx.empty /home/a1/openvela/cmake_out/sf32lb52_devkit_lcd/allsyms_empty.c > /tmp/mkallsyms.err 2>&1
echo "mkallsyms_exit=$?" | tee -a "$LOG"
cat /tmp/mkallsyms.err | tee -a "$LOG"
# also try without file
ls -la nuttx.empty 2>&1 | tee -a "$LOG"
file nuttx.empty 2>&1 | tee -a "$LOG"

# continue build
cd ~/openvela
cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec=$?
echo "cmake_build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  grep -iE 'Error|Traceback|ModuleNotFound|FAILED:' "$LOG" | tail -40 | tee /mnt/hgfs/VMware_share/artifacts/build_errors_tail.txt
fi
exit $ec