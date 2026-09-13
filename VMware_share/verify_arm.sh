#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela
GCC=prebuilts/gcc/linux-x86_64/arm-none-eabi/bin/arm-none-eabi-gcc
echo "=== VERIFY $(date -Iseconds) ==="
ls -la "$GCC"
"$GCC" --version | head -2
du -sh prebuilts/gcc/linux-x86_64/arm-none-eabi
test -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd && echo HAS_DEVKIT_LCD
test -d nuttx && echo HAS_NUTTX
test -d apps && echo HAS_APPS
test -d build && echo HAS_BUILD
# how to build?
ls build.sh ./nuttx/tools/configure.sh 2>/dev/null
head -40 build.sh 2>/dev/null
echo "=== disk ==="
df -h / | tail -1
echo "$PWD/$GCC" > /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
echo GCC_OK > /mnt/hgfs/VMware_share/artifacts/SYNC_ARM_DONE.txt