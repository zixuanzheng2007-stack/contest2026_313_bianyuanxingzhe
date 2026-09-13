#!/bin/bash
set -u
LOG=/mnt/hgfs/VMware_share/artifacts/build_devkit_lcd.log
export PATH="$HOME/bin:$HOME/.local/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$PATH"
mkdir -p ~/bin /tmp/genromfs_deb
cd /tmp/genromfs_deb

echo "==== fetch genromfs deb $(date -Iseconds) ====" | tee -a "$LOG"

# Ubuntu package download without install
apt-get download genromfs >>"$LOG" 2>&1 || true
if ls genromfs_*.deb >/dev/null 2>&1; then
  dpkg-deb -x genromfs_*.deb extracted
  find extracted -type f -name genromfs -exec cp -f {} ~/bin/genromfs \;
fi

if [ ! -x ~/bin/genromfs ]; then
  # compile from known github mirror
  rm -rf /tmp/genromfs_build
  git clone --depth 1 https://github.com/chexum/genromfs.git /tmp/genromfs_build >>"$LOG" 2>&1
  make -C /tmp/genromfs_build -j$(nproc) >>"$LOG" 2>&1
  cp -f /tmp/genromfs_build/genromfs ~/bin/genromfs
  chmod +x ~/bin/genromfs
fi

ls -la ~/bin/genromfs | tee -a "$LOG"
~/bin/genromfs -V 2>&1 | head -5 | tee -a "$LOG" || ~/bin/genromfs 2>&1 | head -5 | tee -a "$LOG"

# also need xxd usually from vim-common - check
command -v xxd || { echo NEED_XXD | tee -a "$LOG"; }

cd ~/openvela
echo "==== resume build $(date -Iseconds) ====" | tee -a "$LOG"
# ensure PATH for ninja/sh subshells: write wrapper into /usr is impossible; use absolute symlink in a PATH dir already used...
# ninja uses /bin/sh which may not have ~/bin. Put genromfs also in /tmp and modify PATH permanently
grep -q 'HOME/bin' ~/.profile 2>/dev/null || echo 'export PATH="$HOME/bin:$PATH"' >> ~/.profile
# Critical: cmake recipes call bare `genromfs` via /bin/sh - PATH may not include ~/bin.
# Create in a common path we can write: use ~/.local/bin which is often in path, AND inject via env in cmake build.
export PATH="$HOME/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"
# Also copy to /home/a1/openvela so we can use env PATH in cmake --build
mkdir -p "$HOME/.local/bin"
cp -f "$HOME/bin/genromfs" "$HOME/.local/bin/genromfs"

# Force PATH for ninja by writing a tiny wrapper script used via ENV
set +e
env PATH="$HOME/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" cmake --build cmake_out/sf32lb52_devkit_lcd >>"$LOG" 2>&1
ec=$?
echo "cmake_build_exit=$ec $(date -Iseconds)" | tee -a "$LOG"
if [ -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin ]; then
  cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
  ls -la cmake_out/sf32lb52_devkit_lcd/nuttx.bin | tee -a "$LOG"
  echo BUILD_OK | tee -a "$LOG" | tee /mnt/hgfs/VMware_share/artifacts/BUILD_OK.txt
else
  grep -E 'FAILED:|not found|error:' "$LOG" | tail -25 > /mnt/hgfs/VMware_share/artifacts/build_errors_tail.txt
  tail -25 "$LOG"
fi
exit $ec