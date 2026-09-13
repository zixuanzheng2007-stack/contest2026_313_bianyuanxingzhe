#!/bin/bash
cd ~/openvela
echo "=== mkallsyms usage ==="
head -80 nuttx/tools/mkallsyms.py
echo "=== cmake refs ==="
rg -n "nuttx\.empty|allsyms_empty|mkallsyms" nuttx/cmake nuttx/CMakeLists.txt 2>/dev/null | head -40
rg -n "nuttx\.empty|allsyms_empty|mkallsyms" cmake_out/sf32lb52_devkit_lcd --glob 'build.ninja' 2>/dev/null | head -40
# check if CONFIG_ALLSYMS
grep -n ALLSYMS vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh/defconfig || true
grep ALLSYMS cmake_out/sf32lb52_devkit_lcd/.config 2>/dev/null || true