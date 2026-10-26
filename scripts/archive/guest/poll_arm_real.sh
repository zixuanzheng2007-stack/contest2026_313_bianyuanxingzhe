#!/bin/bash
# kill hung grep from earlier broken ssh
kill 48264 2>/dev/null || true
# fix poll: only report real gcc
GCC=$(find /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi -type f -name arm-none-eabi-gcc 2>/dev/null | head -1)
echo "time=$(date -Iseconds)"
echo "size=$(du -sh /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null | cut -f1)"
echo "script=$(pgrep -c -f arm_manual_clone.sh || echo 0)"
echo "fetch=$(pgrep -c -f prebuilts_gcc_linux-x86_64_arm-none-eabi || echo 0)"
if [ -n "$GCC" ]; then
  echo "GCC_REAL=$GCC"
  ls -la "$GCC"
  "$GCC" --version 2>&1 | head -2
else
  echo "GCC_REAL=NONE"
fi
# system fallback
command -v arm-none-eabi-gcc >/dev/null && echo "SYS_GCC=$(arm-none-eabi-gcc --version | head -1)" || echo "SYS_GCC=NONE"
# competing syncs
echo "repo_sync_procs=$(pgrep -c -f 'main.py.*sync' || echo 0)"
tail -5 /mnt/hgfs/VMware_share/artifacts/arm_manual_clone.log