#!/bin/bash
echo "=== log tail ==="
tail -12 /mnt/hgfs/VMware_share/artifacts/repo_sync_critical.log 2>/dev/null
echo "=== gcc ==="
find /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | head -3
ls /home/a1/openvela/prebuilts/gcc/linux-x86_64/ 2>/dev/null
echo "=== script ==="
ps -p 38411 >/dev/null 2>&1 && echo RUNNING || echo DONE
pgrep -af 'sync_critical|arm-none-eabi' | head -8
du -sh /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null || echo no_arm_dir_yet
grep -E 'DONE|exit_|HEURISTIC|fatal错误|SyncError|Fetching' /mnt/hgfs/VMware_share/artifacts/repo_sync_critical.log 2>/dev/null | tail -20