#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela || exit 1
echo "=== processes ==="
ps -ef | grep -E 'main.py|git-remote|git fetch' | grep -v grep | head -15 || true
echo "=== disk ==="
df -h / | tail -1
echo "=== sizes ==="
du -sh .repo vendor packages nuttx apps external prebuilts 2>/dev/null || true
echo "=== sifli ==="
if [ -d vendor/sifli ]; then echo HAS_SIFLI; ls vendor/sifli | head; else echo NO_SIFLI; fi
ls vendor 2>/dev/null || true
echo "=== logs ==="
tail -20 /tmp/repo_sync2.log 2>/dev/null || true
tail -20 /mnt/hgfs/VMware_share/artifacts/repo_sync.log 2>/dev/null || true
echo "=== repo list count ==="
timeout 30 repo list 2>/dev/null | wc -l || echo repo_list_timeout
timeout 60 repo status 2>&1 | head -25 || echo repo_status_timeout