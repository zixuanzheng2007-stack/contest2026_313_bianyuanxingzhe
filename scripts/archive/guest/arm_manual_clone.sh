#!/bin/bash
set -u
export PATH="$HOME/bin:$PATH"
unset GIT_CONFIG_GLOBAL
export GIT_TERMINAL_PROMPT=0
cd ~/openvela
LOG=/mnt/hgfs/VMware_share/artifacts/arm_manual_clone.log
mkdir -p /mnt/hgfs/VMware_share/artifacts

echo "==== MANUAL ARM CLONE $(date -Iseconds) ====" | tee "$LOG"

# stop competing syncs
pkill -f arm_only_sync.sh 2>/dev/null || true
pkill -f sync_critical.sh 2>/dev/null || true
pkill -f 'repo sync' 2>/dev/null || true
pkill -f git-remote-https 2>/dev/null || true
sleep 2

# ensure ghproxy
git config --global url."https://ghproxy.net/https://github.com/".insteadOf "https://github.com/"

DEST=prebuilts/gcc/linux-x86_64/arm-none-eabi
URL=https://ghproxy.net/https://github.com/open-vela/prebuilts_gcc_linux-x86_64_arm-none-eabi

if find "$DEST" -name arm-none-eabi-gcc 2>/dev/null | grep -q .; then
  echo ALREADY_OK | tee -a "$LOG"
  find "$DEST" -name arm-none-eabi-gcc | head -1 | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt
  exit 0
fi

# remove incomplete checkout dir if present
rm -rf "$DEST"
mkdir -p prebuilts/gcc/linux-x86_64

echo "cloning $URL -> $DEST" | tee -a "$LOG"
set +e
# shallow clone; retry a few times
for i in 1 2 3 4 5 6 7 8; do
  echo "---- clone attempt $i $(date -Iseconds) ----" | tee -a "$LOG"
  rm -rf "$DEST"
  git clone --depth 1 --single-branch "$URL" "$DEST" >>"$LOG" 2>&1
  ec=$?
  echo "clone_exit=$ec" | tee -a "$LOG"
  if [ $ec -eq 0 ] && find "$DEST" -name arm-none-eabi-gcc 2>/dev/null | grep -q .; then
    echo GCC_OK | tee -a "$LOG"
    find "$DEST" -name arm-none-eabi-gcc | head -1 | tee /mnt/hgfs/VMware_share/artifacts/gcc_path.txt | tee -a "$LOG"
    du -sh "$DEST" | tee -a "$LOG"
    ls "$DEST" | head | tee -a "$LOG"
    echo "==== DONE $(date -Iseconds) ====" | tee -a "$LOG"
    exit 0
  fi
  # partial clone dir may exist
  du -sh "$DEST" 2>/dev/null | tee -a "$LOG"
  sleep 8
done

echo "==== FAIL $(date -Iseconds) ====" | tee -a "$LOG"
# fallback: apt toolchain note
command -v arm-none-eabi-gcc && arm-none-eabi-gcc --version | head -1 | tee -a "$LOG"
exit 1