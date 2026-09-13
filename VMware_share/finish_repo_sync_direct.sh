#!/bin/bash
export PATH="$HOME/bin:$PATH"
# NO mirror - direct GitHub (gitclone 504 broke refs)
unset GIT_CONFIG_GLOBAL
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/repo_sync_direct.log
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== stop broken mirror sync $(date -Iseconds) ====" | tee "$LOG"
pkill -f finish_repo_sync.sh 2>/dev/null || true
pkill -f '/home/a1/openvela/.repo/repo/main.py' 2>/dev/null || true
pkill -f git-remote-https 2>/dev/null || true
sleep 3

echo "==== what we have ====" | tee -a "$LOG"
test -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd && echo HAS_DEVKIT_LCD | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | tee -a "$LOG" | head
repo list 2>/dev/null | wc -l | tee -a "$LOG"

echo "==== sync missing (no fail-fast, j4) $(date -Iseconds) ====" | tee -a "$LOG"
for i in 1 2 3 4 5 6 7 8; do
  echo "---- round $i $(date -Iseconds) ----" | tee -a "$LOG"
  set +e
  # Prefer fetching only what's needed; full sync without fail-fast
  repo sync -c -j4 --no-tags >>"$LOG" 2>&1
  ec=$?
  set -e
  echo "round $i exit=$ec" | tee -a "$LOG"
  # success heuristic: toolchain present + sifli present
  GCC=$(find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | head -1)
  if [ -n "$GCC" ] && [ -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd ]; then
    echo "HEURISTIC_OK gcc=$GCC" | tee -a "$LOG"
    # try one more clean sync
    set +e
    repo sync -c -j4 --no-tags >>"$LOG" 2>&1
    ec2=$?
    set -e
    echo "final_sync_exit=$ec2" | tee -a "$LOG"
    break
  fi
  sleep 8
done

echo "==== DONE $(date -Iseconds) ====" | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | head | tee -a "$LOG"
test -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd && echo HAS_DEVKIT_LCD | tee -a "$LOG"
echo $ec > /mnt/hgfs/VMware_share/artifacts/repo_sync_direct.exit