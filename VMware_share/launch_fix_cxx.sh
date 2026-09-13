#!/bin/bash
nohup bash /mnt/hgfs/VMware_share/fix_cxxfilt_build.sh >/mnt/hgfs/VMware_share/artifacts/fix_cxx_nohup.out 2>&1 &
echo $! > /mnt/hgfs/VMware_share/artifacts/fix_cxx.pid
echo STARTED:$(cat /mnt/hgfs/VMware_share/artifacts/fix_cxx.pid)