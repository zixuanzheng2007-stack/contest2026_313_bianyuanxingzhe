#!/bin/bash
# Kill competing repo syncs but keep arm_manual_clone and its git child
echo "before:"
pgrep -af 'repo sync|main.py|git-remote-https|arm_manual' | head -30

# kill repo sync parent processes (not arm clone)
pkill -f '/home/a1/openvela/.repo/repo/main.py' 2>/dev/null || true
pkill -f 'repo sync' 2>/dev/null || true

# kill https fetches that are NOT arm-none-eabi
for pid in $(pgrep -f git-remote-https); do
  cmd=$(ps -p $pid -o args= 2>/dev/null)
  case "$cmd" in
    *arm-none-eabi*|*prebuilts_gcc_linux-x86_64_arm-none-eabi*) echo "KEEP $pid $cmd" ;;
    *) echo "KILL $pid $cmd"; kill $pid 2>/dev/null || true ;;
  esac
done
sleep 1
echo "after:"
pgrep -af 'git-remote-https|arm_manual|git clone' | head -20 || echo none
du -sh /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null
find /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null
ls -la /home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null | head
tail -20 /mnt/hgfs/VMware_share/artifacts/arm_manual_clone.log