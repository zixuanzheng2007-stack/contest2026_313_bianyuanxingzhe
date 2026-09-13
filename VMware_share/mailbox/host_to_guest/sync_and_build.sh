#!/bin/bash
# 宿主机 newsrc → VM 编译树；支持子目录 skills/ ai_agent_ext/
set -e

SRC=/mnt/hgfs/VMware_share/mailbox/host_to_guest/newsrc
APP=~/openvela/contest2026_313_bianyuanxingzhe/app/edge_walker
OUT=~/openvela/cmake_out/sf32lb52_devkit_lcd
NINJA=~/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja

[ -d "$SRC" ] || { echo "missing $SRC"; exit 1; }

echo "=== sync ==="
rm -f "$APP"/ew_wifi_secret.h "$APP"/*.bak_hold
rsync -a --delete \
  --exclude 'edge_walker/' \
  --exclude '.gitignore' \
  "$SRC"/ "$APP"/
ls "$APP" | tr '\n' ' '
echo

echo "=== host smoke ==="
cd "$APP"
gcc -O2 -Wall -Wextra -o /tmp/host_smoke host_smoke.c ew_ld2451.c
/tmp/host_smoke | tail -3

echo "=== build edge_walker (sf32lb52_devkit_lcd) ==="
cd "$OUT"
"$NINJA" 2>&1 | grep -Ev "^\[[0-9]+/[0-9]+\]" | tail -40
echo "=== result ==="
ls -la "$OUT"/nuttx.bin
cp -f "$OUT/nuttx.bin" /mnt/hgfs/VMware_share/artifacts/nuttx_wifiui.bin
