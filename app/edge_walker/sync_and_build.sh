#!/usr/bin/env bash
# 边缘行者：同步 manifest + 注入 ai_agent Tool + 编译 SF32LB52 ai_agent 固件
set -euo pipefail

OPENVELA="${OPENVELA:-/home/a1/openvela}"
CONTEST="${CONTEST:-$OPENVELA/contest2026_313_bianyuanxingzhe}"
export PATH="$OPENVELA/prebuilts/build-tools/linux-x86_64/bin:$PATH"
EW="$CONTEST/app/edge_walker"
AGENT_PKG="$OPENVELA/packages/ai_agent"
BOARD_CFG="../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/ai_agent"
BUILD_DIR="$OPENVELA/cmake_out/sf32lb52_devkit_lcd_ai_agent"
IPC_SRC="$EW/ai_agent_ext/tool_approach_alert_ipc.c"
IPC_DST="$AGENT_PKG/src/tools/tool_approach_alert_ipc.c"
HDR_SRC="$EW/ai_agent_ext/tool_approach_alert.h"
HDR_DST="$AGENT_PKG/src/tools/tool_approach_alert.h"
REGISTRY="$AGENT_PKG/src/tools/tool_registry.c"
CMakelists="$AGENT_PKG/CMakeLists.txt"
MAKEFILE="$AGENT_PKG/Makefile"
STAMP="$BUILD_DIR/.ew_agent_patch_stamp"

echo "[sync_and_build] openvela=$OPENVELA contest=$CONTEST"

# 自动化默认跳过 repo sync（避免 git user.name 未配导致失败）
# 需要同步时：SKIP_REPO_SYNC=0 bash sync_and_build.sh
if [[ "${SKIP_REPO_SYNC:-1}" != "1" && -d "$OPENVELA/.repo" ]]; then
  echo "[sync_and_build] repo sync (contest manifest)..."
  (cd "$OPENVELA" && repo sync -c -j"$(nproc)" contest2026_313_bianyuanxingzhe) || {
    echo "[sync_and_build] WARN: repo sync failed, continue build anyway"
  }
else
  echo "[sync_and_build] skip repo sync (SKIP_REPO_SYNC=${SKIP_REPO_SYNC:-1})"
fi

echo "[sync_and_build] inject approach_alert tool into packages/ai_agent..."
cp -f "$IPC_SRC" "$IPC_DST"
cp -f "$HDR_SRC" "$HDR_DST"

if ! grep -q 'tool_approach_alert_ipc.c' "$CMakelists"; then
  sed -i '/src\/tools\/tool_control.c/a\    src/tools/tool_approach_alert_ipc.c' "$CMakelists"
fi

if ! grep -q 'tool_approach_alert_ipc.c' "$MAKEFILE" 2>/dev/null; then
  if grep -q 'tool_control.c' "$MAKEFILE" 2>/dev/null; then
    sed -i '/tool_control.c/a CSRCS += src/tools/tool_approach_alert_ipc.c' "$MAKEFILE"
  fi
fi

if ! grep -q 'tool_approach_alert.h' "$REGISTRY"; then
  sed -i '/#include "tools\/tool_control.h"/a #include "tools/tool_approach_alert.h"' "$REGISTRY"
fi

if ! grep -q 'approach_alert' "$REGISTRY"; then
  sed -i '/tool_launch_quickapp_execute/r '"$EW/ai_agent_ext/patch_tool_registry.snip" "$REGISTRY"
fi

touch "$STAMP"

echo "[sync_and_build] cmake configure..."
cmake -B "$BUILD_DIR" -S "$OPENVELA/nuttx" -GNinja \
  -DBOARD_CONFIG="$BOARD_CFG" \
  -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations"

echo "[sync_and_build] build..."
cmake --build "$BUILD_DIR" -j"$(nproc)"

echo "[sync_and_build] OK → $BUILD_DIR/nuttx.bin"
ls -lh "$BUILD_DIR/nuttx.bin"
