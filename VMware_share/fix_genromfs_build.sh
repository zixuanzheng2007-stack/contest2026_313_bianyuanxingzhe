#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
cd ~/openvela

echo "==== install genromfs $(date -Iseconds) ====" | tee -a "$LOG"
# try passwordless sudo first
if sudo -n true 2>/dev/null; then
  sudo -n apt-get install -y genromfs >>"$LOG" 2>&1
fi

if ! command -v genromfs >/dev/null; then
  # build from source into ~/bin
  mkdir -p /tmp/genromfs_src ~/bin
  cd /tmp/genromfs_src
  if [ ! -f genromfs-0.5.2.tar.gz ]; then
    curl -fsSL -o genromfs-0.5.2.tar.gz https://sourceforge.net/projects/romfs/files/genromfs/0.5.2/genromfs-0.5.2.tar.gz/download || \
    curl -fsSL -o genromfs-0.5.2.tar.gz https://github.com/chexum/genromfs/archive/refs/tags/0.5.2.tar.gz || true
  fi
  # fallback: clone
  if [ ! -f genromfs-0.5.2.tar.gz ]; then
    git clone --depth 1 https://github.com/chexum/genromfs.git genromfs-src >>"$LOG" 2>&1
    cd genromfs-src
  else
    tar xzf genromfs-0.5.2.tar.gz
    cd genromfs-* 2>/dev/null || cd genromfs-src
  fi
  make -j$(nproc) >>"$LOG" 2>&1
  cp -f genromfs ~/bin/genromfs
  chmod +x ~/bin/genromfs
fi

command -v genromfs | tee -a "$LOG"
genromfs -h 2>&1 | head -3 | tee -a "$LOG"

cd ~/openvela
echo "==== resume after genromfs $(date -Iseconds) ====" | tee -a "$LOG"
set +e
cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec=$?
echo "cmake_build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  grep -E 'FAILED:|not found|error:' "$LOG" | tail -20 > /mnt/hgfs/VMware_share/artifacts/build_errors_tail.txt
  tail -30 "$LOG"
fi
exit $ec