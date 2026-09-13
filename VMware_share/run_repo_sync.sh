#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela || exit 1
mkdir -p /mnt/hgfs/VMware_share/artifacts
echo "==== sync start $(date -Iseconds) ====" | tee /mnt/hgfs/VMware_share/artifacts/repo_sync.log
repo sync -c -j$(nproc) >> /mnt/hgfs/VMware_share/artifacts/repo_sync.log 2>&1
ec=$?
echo "==== sync done $(date -Iseconds) exit=$ec ====" | tee -a /mnt/hgfs/VMware_share/artifacts/repo_sync.log
if [ -d vendor/sifli ]; then echo HAS_SIFLI >> /mnt/hgfs/VMware_share/artifacts/repo_sync.log; fi
find vendor/sifli -iname '*devkit_lcd*' 2>/dev/null | head >> /mnt/hgfs/VMware_share/artifacts/repo_sync.log
echo $ec > /mnt/hgfs/VMware_share/artifacts/repo_sync.exit