#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/arm_gitcode_clone.log
DEST=prebuilts/gcc/linux-x86_64/arm-none-eabi

echo "==== PHASE0 system fallback $(date -Iseconds) ====" | tee -a "$LOG"
# Always ensure fallback path exists for build; replace later if real clone succeeds
if command -v arm-none-eabi-gcc >/dev/null; then
  mkdir -p "$DEST/bin"
  for b in ar as gcc g++ c++ ld nm objcopy objdump ranlib readelf size strip gdb gcov; do
    [ -x "/usr/bin/arm-none-eabi-$b" ] && ln -sfn "/usr/bin/arm-none-eabi-$b" "$DEST/bin/arm-none-eabi-$b"
  done
  echo "FALLBACK_READY" | tee -a "$LOG"
  /usr/bin/arm-none-eabi-gcc --version | head -1 | tee -a "$LOG"
  echo "/usr/bin/arm-none-eabi-gcc" > /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
fi

# Stop ONLY python repo sync workers; do NOT blanket-kill git-remote-https after we start
pkill -f '/home/a1/openvela/.repo/repo/main.py' 2>/dev/null || true
# If another arm clone already running for gitcode, exit
if pgrep -f 'git clone.*prebuilts_gcc_linux-x86_64_arm-none-eabi' >/dev/null; then
  echo "CLONE_ALREADY_RUNNING" | tee -a "$LOG"
  exit 0
fi

# Move fallback aside; clone into DEST
FB=/tmp/arm_none_eabi_fallback_bin
rm -rf "$FB"
mkdir -p "$FB"
if [ -d "$DEST/bin" ]; then cp -a "$DEST/bin/." "$FB/" 2>/dev/null || true; fi

# Only remove DEST if it looks incomplete (no real gcc binary owned by tree, only symlinks)
REAL=$(find "$DEST" -type f -name arm-none-eabi-gcc 2>/dev/null | head -1)
if [ -n "$REAL" ]; then
  echo "REAL_GCC_PRESENT=$REAL" | tee -a "$LOG"
  exit 0
fi

rm -rf "$DEST"
mkdir -p prebuilts/gcc/linux-x86_64

URL="https://gitcode.com/open-vela/prebuilts_gcc_linux-x86_64_arm-none-eabi.git"
echo "---- gitcode clone $(date -Iseconds) ----" | tee -a "$LOG"
set +e
git clone --depth 1 --single-branch --progress "$URL" "$DEST" >>"$LOG" 2>&1
ec=$?
set -e
echo "clone_exit=$ec $(date -Iseconds)" | tee -a "$LOG"

GCC=$(find "$DEST" -type f -name arm-none-eabi-gcc 2>/dev/null | head -1)
if [ -n "$GCC" ]; then
  echo "GCC_OK=$GCC" | tee -a "$LOG"
  echo "$GCC" > /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
  "$GCC" --version | head -1 | tee -a "$LOG"
  du -sh "$DEST" | tee -a "$LOG"
  echo "==== PREBUILT_DONE $(date -Iseconds) ====" | tee -a "$LOG"
  exit 0
fi

echo "clone failed; restore fallback symlinks" | tee -a "$LOG"
mkdir -p "$DEST/bin"
cp -a "$FB/." "$DEST/bin/" 2>/dev/null || true
# recreate if needed
for b in ar as gcc g++ c++ ld nm objcopy objdump ranlib readelf size strip; do
  [ -x "/usr/bin/arm-none-eabi-$b" ] && ln -sfn "/usr/bin/arm-none-eabi-$b" "$DEST/bin/arm-none-eabi-$b"
done
echo "FALLBACK_RESTORED" | tee -a "$LOG"
exit 0