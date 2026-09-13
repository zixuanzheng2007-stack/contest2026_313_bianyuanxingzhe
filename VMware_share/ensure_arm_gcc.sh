#!/bin/bash
export PATH="$HOME/bin:$PATH"
unset GIT_CONFIG_GLOBAL
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/arm_gcc_sync.log

# If already fetching arm-none-eabi, just wait
if pgrep -f 'prebuilts_gcc_linux-x86_64_arm-none-eabi' >/dev/null; then
  echo "FETCH_IN_PROGRESS $(date -Iseconds)" | tee -a "$LOG"
  exit 0
fi

# If gcc already present, done
if find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | grep -q .; then
  echo "ALREADY_OK $(date -Iseconds)" | tee -a "$LOG"
  find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc | head -1 | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
  exit 0
fi

echo "START_ARM_SYNC $(date -Iseconds)" | tee "$LOG"
# Do not kill other syncs; just sync this one project
repo sync -n -c -j1 --no-tags prebuilts/gcc/linux-x86_64/arm-none-eabi >>"$LOG" 2>&1
ec=$?
echo "ARM_SYNC_EXIT=$ec $(date -Iseconds)" | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | tee -a "$LOG" | head -1 | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
ls prebuilts/gcc/linux-x86_64/ | tee -a "$LOG"
du -sh prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null | tee -a "$LOG"