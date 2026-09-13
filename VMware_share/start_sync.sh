#!/bin/bash
mkdir -p /mnt/hgfs/VMware_share/artifacts
pkill -f '/mnt/hgfs/VMware_share/run_repo_sync.sh' 2>/dev/null || true
nohup bash /mnt/hgfs/VMware_share/run_repo_sync.sh > /mnt/hgfs/VMware_share/artifacts/sync_nohup.out 2>&1 &
echo "PID=$!"
sleep 4
ps -ef | grep repo | grep -v grep | head -15
ls -la /mnt/hgfs/VMware_share/artifacts/
tail -n 15 /mnt/hgfs/VMware_share/artifacts/repo_sync.log 2>/dev/null || true