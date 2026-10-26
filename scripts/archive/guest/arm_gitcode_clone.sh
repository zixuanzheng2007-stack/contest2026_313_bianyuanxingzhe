#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/arm_gitcode_clone.log

echo "==== GITCODE ARM $(date -Iseconds) ====" | tee "$LOG"

# stop ALL competing network pulls except we will restart our own
pkill -f arm_manual_clone.sh 2>/dev/null || true
pkill -f 'main.py.*sync' 2>/dev/null || true
pkill -f git-remote-https 2>/dev/null || true
pkill -f 'git clone' 2>/dev/null || true
sleep 3

DEST=prebuilts/gcc/linux-x86_64/arm-none-eabi
# Prefer AtomGit/gitcode (CN) then ghproxy
URLS=(
  "https://gitcode.com/open-vela/prebuilts_gcc_linux-x86_64_arm-none-eabi.git"
  "https://ghproxy.net/https://github.com/open-vela/prebuilts_gcc_linux-x86_64_arm-none-eabi"
  "https://github.com/open-vela/prebuilts_gcc_linux-x86_64_arm-none-eabi"
)

# Remove incomplete dest (only .git so far)
rm -rf "$DEST"
mkdir -p prebuilts/gcc/linux-x86_64

for URL in "${URLS[@]}"; do
  echo "---- try $URL $(date -Iseconds) ----" | tee -a "$LOG"
  rm -rf "$DEST"
  # test connectivity quickly
  if ! curl -I --connect-timeout 8 -s "$URL" >/dev/null 2>&1 && ! curl -I --connect-timeout 8 -s "${URL%.git}" >/dev/null 2>&1; then
    echo "skip unreachable $URL" | tee -a "$LOG"
  fi
  set +e
  timeout 900 git clone --depth 1 --single-branch --progress "$URL" "$DEST" >>"$LOG" 2>&1
  ec=$?
  set -e
  echo "clone_exit=$ec size=$(du -sh "$DEST" 2>/dev/null | cut -f1)" | tee -a "$LOG"
  GCC=$(find "$DEST" -type f -name arm-none-eabi-gcc 2>/dev/null | head -1)
  if [ -n "$GCC" ]; then
    echo "GCC_OK=$GCC" | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
    "$GCC" --version | head -1 | tee -a "$LOG"
    echo "==== DONE $(date -Iseconds) ====" | tee -a "$LOG"
    exit 0
  fi
done

echo "==== PREBUILT_FAIL; linking system gcc fallback $(date -Iseconds) ====" | tee -a "$LOG"
if command -v arm-none-eabi-gcc >/dev/null; then
  rm -rf "$DEST"
  mkdir -p "$DEST/bin"
  for b in ar as gcc g++ ld nm objcopy objdump ranlib readelf size strip gdb; do
    if [ -x "/usr/bin/arm-none-eabi-$b" ]; then
      ln -sf "/usr/bin/arm-none-eabi-$b" "$DEST/bin/arm-none-eabi-$b"
    fi
  done
  # also common names without prefix in some trees
  ln -sf /usr/bin/arm-none-eabi-gcc "$DEST/bin/arm-none-eabi-gcc"
  echo "FALLBACK_SYS_GCC" | tee -a "$LOG"
  ls -la "$DEST/bin" | tee -a "$LOG"
  echo "/usr/bin/arm-none-eabi-gcc" > /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
  arm-none-eabi-gcc --version | head -1 | tee -a "$LOG"
  exit 0
fi
echo FAIL | tee -a "$LOG"
exit 1