#!/bin/bash
nohup bash /mnt/hgfs/VMware_share/fix_genromfs_build.sh >/mnt/hgfs/VMware_share/artifacts/fix_gen_nohup.out 2>&1 &
echo $! > /mnt/hgfs/VMware_share/artifacts/fix_gen.pid
echo STARTED:$(cat /mnt/hgfs/VMware_share/artifacts/fix_gen.pid)