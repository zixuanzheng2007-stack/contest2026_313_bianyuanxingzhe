#!/usr/bin/env bash
# Guest：应用 wifi_fix 补丁并编译 nuttx_wifiui.bin
set -euo pipefail

CONTEST="${CONTEST:-/home/a1/openvela/contest2026_313_bianyuanxingzhe}"
SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
PATCH="$SHARE/mailbox/host_to_guest/wifi_fix"
EW="$CONTEST/app/edge_walker"
EW_OUT="${EW_OUT:-$HOME/openvela/cmake_out/sf32lb52_devkit_lcd}"
NINJA="$HOME/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja"
ART="$SHARE/artifacts/nuttx_wifiui.bin"

export PATH="$HOME/openvela/prebuilts/build-tools/linux-x86_64/bin:$PATH"

echo "=== run_ew_wifiui_build ==="

if [[ -d "$PATCH" ]]; then
  echo "=== apply wifi_fix patch ==="
  cp -f "$PATCH"/ew_wifi_at.c "$PATCH"/ew_wifi_at.h "$PATCH"/ew_wifi_ui.c "$EW"/
  ls -la "$EW"/ew_wifi_*.c "$EW"/ew_wifi_at.h
else
  echo "WARN: no $PATCH, build with existing tree"
fi

if [[ ! -x "$NINJA" ]]; then
  echo "ERROR: ninja missing $NINJA"
  exit 1
fi

cd "$EW_OUT"
echo "=== ninja edge_walker ==="
"$NINJA" 2>&1 | tail -35

if [[ ! -f "$EW_OUT/nuttx.bin" ]]; then
  echo "ERROR: nuttx.bin missing"
  exit 1
fi

mkdir -p "$(dirname "$ART")"
cp -f "$EW_OUT/nuttx.bin" "$ART"
ls -la "$ART"
echo "=== run_ew_wifiui_build OK ==="
