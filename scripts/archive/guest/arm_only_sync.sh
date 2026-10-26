#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
unset GIT_CONFIG_GLOBAL
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/arm_only_sync.log
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== ARM_ONLY stop leftover $(date -Iseconds) ====" | tee "$LOG"
# Stop only leftover full sync / stuck contest fetch; keep nothing else critical
pkill -f 'repo sync -n -c -j4' 2>/dev/null || true
pkill -f 'contest2026_313_bianyuanxingzhe' 2>/dev/null || true
# Stop parent sync_critical if still in leftover phase
if pgrep -f sync_critical.sh >/dev/null; then
  pkill -f sync_critical.sh 2>/dev/null || true
fi
sleep 2

# Prefer ghproxy if direct github is flaky
if curl -I --connect-timeout 6 -s https://ghproxy.net/ >/dev/null 2>&1; then
  git config --global url."https://ghproxy.net/https://github.com/".insteadOf "https://github.com/"
  echo "enabled ghproxy insteadOf" | tee -a "$LOG"
fi

echo "==== pack before $(date -Iseconds) ====" | tee -a "$LOG"
du -sh .repo/project-objects/prebuilts_gcc_linux-x86_64_arm-none-eabi.git 2>/dev/null | tee -a "$LOG"
ls -lah .repo/project-objects/prebuilts_gcc_linux-x86_64_arm-none-eabi.git/objects/pack/ 2>/dev/null | tee -a "$LOG"

for i in 1 2 3 4 5; do
  echo "---- attempt $i $(date -Iseconds) ----" | tee -a "$LOG"
  set +e
  repo sync -n -c -j1 --no-tags --fail-fast prebuilts/gcc/linux-x86_64/arm-none-eabi >>"$LOG" 2>&1
  ec=$?
  set -e
  echo "exit=$ec" | tee -a "$LOG"
  if find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | grep -q .; then
    echo "GCC_OK" | tee -a "$LOG"
    find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc | head -1 | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
    break
  fi
  sleep 5
done

echo "==== verify $(date -Iseconds) ====" | tee -a "$LOG"
ls prebuilts/gcc/linux-x86_64/ 2>/dev/null | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64/arm-none-eabi -name arm-none-eabi-gcc 2>/dev/null | tee -a "$LOG"
du -sh prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null | tee -a "$LOG"
# remove insteadOf to avoid surprising other remotes later? keep for now while syncing
echo "==== ARM_ONLY_DONE $(date -Iseconds) ====" | tee -a "$LOG"