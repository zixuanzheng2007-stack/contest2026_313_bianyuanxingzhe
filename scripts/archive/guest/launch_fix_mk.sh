#!/bin/bash
nohup bash /mnt/hgfs/VMware_share/fix_mkallsyms_build.sh >/mnt/hgfs/VMware_share/artifacts/fix_mk_nohup.out 2>&1 &
echo $! > /mnt/hgfs/VMware_share/artifacts/fix_mk.pid
echo STARTED:$(cat /mnt/hgfs/VMware_share/artifacts/fix_mk.pid)