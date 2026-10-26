#!/bin/bash
set -e
export PATH="$HOME/bin:$PATH"
export GIT_CONFIG_GLOBAL=/mnt/hgfs/VMware_share/gitconfig-mirror
export GIT_TERMINAL_PROMPT=0
cd ~/openvela

LOG=/mnt/hgfs/VMware_share/artifacts/repo_sync_mirror.log
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== kill old sync $(date -Iseconds) ====" | tee "$LOG"
# kill previous repo sync parents (careful: only repo sync)
pkill -f '/home/a1/openvela/.repo/repo/main.py' 2>/dev/null || true
pkill -f 'git-remote-https' 2>/dev/null || true
sleep 2

echo "==== sync attempt $(date -Iseconds) ====" | tee -a "$LOG"
# retry loop
for i in 1 2 3 4 5; do
  echo "---- round $i $(date -Iseconds) ----" | tee -a "$LOG"
  set +e
  repo sync -c -j4 --no-tags --fail-fast >>"$LOG" 2>&1
  ec=$?
  set -e
  echo "round $i exit=$ec" | tee -a "$LOG"
  if [ $ec -eq 0 ]; then
    break
  fi
  echo "retry after failures..." | tee -a "$LOG"
  sleep 5
done

echo "==== verify $(date -Iseconds) ====" | tee -a "$LOG"
repo list | wc -l | tee -a "$LOG"
test -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd && echo HAS_DEVKIT_LCD | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | head | tee -a "$LOG"
# remaining missing?
set +e
repo status -j4 2>&1 | grep -E 'missing|project ' | head -40 | tee -a "$LOG"
echo "==== DONE $(date -Iseconds) ====" | tee -a "$LOG"
echo $ec > /mnt/hgfs/VMware_share/artifacts/repo_sync_mirror.exit