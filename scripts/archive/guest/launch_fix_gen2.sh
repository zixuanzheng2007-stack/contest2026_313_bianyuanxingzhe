#!/bin/bash
nohup bash /mnt/hgfs/VMware_share/fix_genromfs2.sh >/mnt/hgfs/VMware_share/artifacts/fix_gen2_nohup.out 2>&1 &
echo $! > /mnt/hgfs/VMware_share/artifacts/fix_gen2.pid
echo STARTED:$(cat /mnt/hgfs/VMware_share/artifacts/fix_gen2.pid)