#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela
echo "=== manifest grep arm-none ==="
grep -n "arm-none-eabi" .repo/manifests/*.xml .repo/manifest.xml 2>/dev/null | head -20
echo "=== repo list arm ==="
repo list 2>/dev/null | grep -i arm-none || true
echo "=== projects dir ==="
ls -la .repo/projects/prebuilts/gcc/linux-x86_64/ 2>/dev/null
echo "=== local manifest / copy ==="
ls .repo/local_manifests 2>/dev/null
echo "=== git remote in project ==="
git --git-dir=.repo/projects/prebuilts/gcc/linux-x86_64/arm-none-eabi.git remote -v 2>&1 | head
git --git-dir=.repo/projects/prebuilts/gcc/linux-x86_64/arm-none-eabi.git status 2>&1 | head
echo "=== object refs ==="
git --git-dir=.repo/project-objects/prebuilts_gcc_linux-x86_64_arm-none-eabi.git show-ref 2>&1 | head -20
echo "=== HEAD ==="
git --git-dir=.repo/project-objects/prebuilts_gcc_linux-x86_64_arm-none-eabi.git rev-parse HEAD 2>&1
echo "=== current arm_only log ==="
tail -40 /mnt/hgfs/VMware_share/artifacts/arm_only_sync.log