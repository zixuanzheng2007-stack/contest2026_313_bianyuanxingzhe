#!/bin/bash
pkill -f 'build_with_pip.sh|build_devkit_cmake.sh|build_fix_kconfig.sh' 2>/dev/null || true
sleep 1
nohup bash /mnt/hgfs/VMware_share/build_fix_kconfig.sh >/mnt/hgfs/VMware_share/artifacts/build_fix_nohup.out 2>&1 &
echo $! > /mnt/hgfs/VMware_share/artifacts/build_fix.pid
echo STARTED:$(cat /mnt/hgfs/VMware_share/artifacts/build_fix.pid)