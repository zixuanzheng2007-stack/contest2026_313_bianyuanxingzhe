#!/bin/bash
export PATH="$HOME/bin:$PATH"
echo "=== $(date -Iseconds) ==="
pgrep -af arm_manual_clone | head -3 || echo no_script
pgrep -af git-remote-https | head -5 || echo no_https
du -sh /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null || echo no_dest
if find /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | head -1; then
  echo GCC_FOUND
fi
tail -8 /mnt/hgfs/VMware_share/artifacts/arm_manual_clone.log 2>/dev/null