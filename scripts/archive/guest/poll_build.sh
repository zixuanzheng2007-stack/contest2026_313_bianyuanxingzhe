#!/bin/bash
echo "=== $(date -Iseconds) ==="
pgrep -af 'build_devkit_cmake.sh|cmake --build|ninja' | grep -v pgrep | head -8 || echo no_build
tail -20 /mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
echo ---MARKERS---
grep -E 'cmake_configure_exit|cmake_build_exit|BUILD_OK|CONFIG_FAIL|NO_BIN|kconfiglib_ok' /mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log | tail -15
test -f /home/a1/openvela/cmake_out/sf32lb52_devkit_lcd/nuttx.bin && ls -la /home/a1/openvela/cmake_out/sf32lb52_devkit_lcd/nuttx.bin