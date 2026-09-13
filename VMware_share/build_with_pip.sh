#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"
cd ~/openvela

echo "==== get pip $(date -Iseconds) ====" | tee -a "$LOG"

# try ensurepip
python3 -m ensurepip --user >>"$LOG" 2>&1 || true

# try get-pip.py
if ! python3 -m pip --version >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py >>"$LOG" 2>&1
  python3 /tmp/get-pip.py --user >>"$LOG" 2>&1
fi

python3 -m pip --version | tee -a "$LOG"
python3 -m pip install --user kconfiglib pyelftools >>"$LOG" 2>&1
python3 -c "import kconfiglib; print('kconfiglib_ok')" | tee -a "$LOG"

# also try apt if passwordless sudo
if ! python3 -c "import kconfiglib" 2>/dev/null; then
  sudo -n apt-get update >>"$LOG" 2>&1
  sudo -n apt-get install -y python3-pip python3-kconfiglib >>"$LOG" 2>&1 || true
fi

python3 -c "import kconfiglib; print('kconfiglib_ok2')" | tee -a "$LOG" || echo NEED_KCONFIGLIB | tee -a "$LOG"

if ! python3 -c "import kconfiglib" 2>/dev/null; then
  exit 2
fi

export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
echo "==== CMAKE BUILD $(date -Iseconds) ====" | tee -a "$LOG"
rm -f nuttx/.config nuttx/.config.old nuttx/.version
rm -rf cmake_out/sf32lb52_devkit_lcd
set +e
cmake -B cmake_out/sf32lb52_devkit_lcd -S "$PWD/nuttx" -GNinja \
  -DBOARD_CONFIG=../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh \
  -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations" >>"$LOG" 2>&1
ec_cfg=$?
echo "cmake_configure_exit=$ec_cfg $(date -Iseconds)" | tee -a "$LOG"
[ $ec_cfg -ne 0 ] && { tail -40 "$LOG"; exit $ec_cfg; }

cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec_bld=$?
echo "cmake_build_exit=$ec_bld $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
fi
exit $ec_bld