#!/bin/bash
export PATH="$HOME/bin:$PATH"
unset GIT_CONFIG_GLOBAL
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/repo_sync_critical.log
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== stop previous $(date -Iseconds) ====" | tee "$LOG"
pkill -f finish_repo_sync_direct.sh 2>/dev/null || true
pkill -f finish_repo_sync.sh 2>/dev/null || true
pkill -f '/home/a1/openvela/.repo/repo/main.py' 2>/dev/null || true
pkill -f git-remote-https 2>/dev/null || true
sleep 3

echo "==== sync critical projects with -n (no manifest update) ====" | tee -a "$LOG"
# Critical for SF32 build
TARGETS=(
  "prebuilts/gcc/linux-x86_64/arm-none-eabi"
  "prebuilts/gcc/linux-x86_64/riscv-none-elf"
  "vendor/sifli"
  "vendor/sifli/boards/sf32lb52/libs"
  "nuttx"
  "apps"
  "build"
  "packages"
  "frameworks"
  "external"
)

for t in "${TARGETS[@]}"; do
  echo "---- sync $t $(date -Iseconds) ----" | tee -a "$LOG"
  set +e
  repo sync -n -c -j2 --no-tags "$t" >>"$LOG" 2>&1
  echo "exit_$t=$?" | tee -a "$LOG"
  set -e
done

echo "==== full leftover sync -n j4 ====" | tee -a "$LOG"
set +e
repo sync -n -c -j4 --no-tags >>"$LOG" 2>&1
echo "full_exit=$?" | tee -a "$LOG"
set -e

echo "==== verify ====" | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | tee -a "$LOG"
ls -la prebuilts/gcc/linux-x86_64/ | tee -a "$LOG"
test -d vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd && echo HAS_DEVKIT_LCD | tee -a "$LOG"
du -sh prebuilts/gcc/linux-x86_64/arm-none-eabi 2>/dev/null | tee -a "$LOG"
echo "==== DONE $(date -Iseconds) ====" | tee -a "$LOG"
find prebuilts/gcc/linux-x86_64 -name arm-none-eabi-gcc 2>/dev/null | head -1 > /mnt/hgfs/VMware_share/artifacts/gcc_path.txt