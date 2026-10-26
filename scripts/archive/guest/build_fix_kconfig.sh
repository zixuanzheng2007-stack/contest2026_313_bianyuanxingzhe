#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela

echo "==== venv+pip $(date -Iseconds) ====" | tee -a "$LOG"

# Prefer break-system-packages for the python cmake will use
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
python3 /tmp/get-pip.py --user --break-system-packages >>"$LOG" 2>&1
python3 -m pip install --user --break-system-packages kconfiglib pyelftools >>"$LOG" 2>&1
python3 -c "import kconfiglib; print('kconfiglib_ok', getattr(kconfiglib,'__version__', '?'))" | tee -a "$LOG"

# Also make a venv as backup and prepend to PATH
python3 -m venv /home/a1/openvela/.venv >>"$LOG" 2>&1 || true
if [ -x /home/a1/openvela/.venv/bin/pip ]; then
  /home/a1/openvela/.venv/bin/pip install -U kconfiglib pyelftools >>"$LOG" 2>&1
fi

if ! python3 -c "import kconfiglib" 2>/dev/null; then
  echo KCONFIG_STILL_MISSING | tee -a "$LOG"
  # last resort: add venv site-packages to PYTHONPATH for system python
  SITE=$(/home/a1/openvela/.venv/bin/python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null)
  export PYTHONPATH="$SITE:${PYTHONPATH:-}"
  python3 -c "import kconfiglib; print('kconfiglib_via_PYTHONPATH')" | tee -a "$LOG" || exit 2
fi

echo "==== CMAKE BUILD $(date -Iseconds) ====" | tee -a "$LOG"
rm -f nuttx/.config nuttx/.config.old nuttx/.version
rm -rf cmake_out/sf32lb52_devkit_lcd
set +e
cmake -B cmake_out/sf32lb52_devkit_lcd -S "$PWD/nuttx" -GNinja \
  -DBOARD_CONFIG=../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh \
  -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations" >>"$LOG" 2>&1
ec_cfg=$?
echo "cmake_configure_exit=$ec_cfg $(date -Iseconds)" | tee -a "$LOG"
if [ $ec_cfg -ne 0 ]; then tail -50 "$LOG"; exit $ec_cfg; fi

cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec_bld=$?
echo "cmake_build_exit=$ec_bld $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
fi
exit $ec_bld