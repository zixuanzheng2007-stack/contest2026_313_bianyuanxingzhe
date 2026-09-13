#!/usr/bin/env bash
# Guest：编译 edge_walker（newsrc 同步）或 ai_agent 配置包（若存在 out 目录）
set -euo pipefail

CONTEST="${CONTEST:-/home/a1/openvela/contest2026_313_bianyuanxingzhe}"
SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
SYNC="$SHARE/mailbox/host_to_guest/sync_and_build.sh"
AI_OUT=~/openvela/cmake_out/sf32lb52_devkit_lcd_ai_agent
EW_OUT=~/openvela/cmake_out/sf32lb52_devkit_lcd
NINJA=~/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja

echo "=== run_ew_agent_build ==="

if [[ -x "$SYNC" ]] || [[ -f "$SYNC" ]]; then
  echo "=== sync edge_walker (newsrc) ==="
  tr -d '\r' < "$SYNC" | bash
fi

if [[ -d "$AI_OUT" && -f "$NINJA" ]]; then
  echo "=== build ai_agent out ==="
  cd "$AI_OUT"
  "$NINJA" 2>&1 | tail -30
  if [[ -f "$AI_OUT/nuttx.bin" ]]; then
    cp -f "$AI_OUT/nuttx.bin" "$SHARE/artifacts/nuttx_ai_agent.bin"
    ls -la "$SHARE/artifacts/nuttx_ai_agent.bin"
    exit 0
  fi
fi

if [[ -f "$EW_OUT/nuttx.bin" ]]; then
  echo "=== fallback: copy edge_walker nuttx.bin ==="
  cp -f "$EW_OUT/nuttx.bin" "$SHARE/artifacts/nuttx_ai_agent.bin"
  ls -la "$SHARE/artifacts/nuttx_ai_agent.bin"
  exit 0
fi

echo "ERROR: no nuttx.bin produced"
exit 1
