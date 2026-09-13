#!/bin/bash
set -u
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log

echo "==== install deps $(date -Iseconds) ====" | tee -a "$LOG"
python3 -m pip install --user -U pip kconfiglib pyelftools >>"$LOG" 2>&1
python3 -c "import kconfiglib; print('kconfiglib_ok', kconfiglib.__version__)" | tee -a "$LOG"

echo "==== CMAKE BUILD RETRY $(date -Iseconds) ====" | tee -a "$LOG"
rm -f nuttx/.config nuttx/.config.old nuttx/.version
rm -rf cmake_out/sf32lb52_devkit_lcd

set +e
cmake -B cmake_out/sf32lb52_devkit_lcd -S "$PWD/nuttx" -GNinja \
  -DBOARD_CONFIG=../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh \
  -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations" >>"$LOG" 2>&1
ec_cfg=$?
echo "cmake_configure_exit=$ec_cfg $(date -Iseconds)" | tee -a "$LOG"
[ $ec_cfg -ne 0 ] && { tail -60 "$LOG"; echo CONFIG_FAIL | tee -a "$LOG"; exit $ec_cfg; }

cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec_bld=$?
echo "cmake_build_exit=$ec_bld $(date -Iseconds)" | tee -a "$LOG"

if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la /mnt/hgfs/VMware_share/artifacts/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  echo NO_BIN | tee -a "$LOG"
  # show last errors
  grep -iE 'error:|fatal|failed' "$LOG" | tail -40
fi
exit $ec_bld