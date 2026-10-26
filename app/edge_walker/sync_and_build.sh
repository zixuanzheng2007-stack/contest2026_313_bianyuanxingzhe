#!/usr/bin/env bash
# 边缘行者：同步 manifest + 注入 ai_agent Tool + 编译 SF32LB52 ai_agent 固件
set -euo pipefail

OPENVELA="${OPENVELA:-/home/a1/openvela}"
CONTEST="${CONTEST:-$OPENVELA/contest2026_313_bianyuanxingzhe}"
export PATH="$HOME/bin:$HOME/.local/bin:$OPENVELA/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$OPENVELA/prebuilts/build-tools/linux-x86_64/bin:$PATH"
EW="$CONTEST/app/edge_walker"
AGENT_PKG="$OPENVELA/packages/ai_agent"
BOARD_CFG="../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/ai_agent"
BUILD_DIR="$OPENVELA/cmake_out/sf32lb52_devkit_lcd_ai_agent"
IPC_SRC="$EW/ai_agent_ext/tool_approach_alert_ipc.c"
IPC_DST="$AGENT_PKG/src/tools/tool_approach_alert_ipc.c"
HDR_SRC="$EW/ai_agent_ext/tool_approach_alert.h"
HDR_DST="$AGENT_PKG/src/tools/tool_approach_alert.h"
IPC_HDR_SRC="$EW/ai_agent_ext/ew_alert_ipc.h"
IPC_HDR_DST="$AGENT_PKG/src/tools/ew_alert_ipc.h"
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
for required in "$IPC_SRC" "$HDR_SRC" "$IPC_HDR_SRC" "$REGISTRY" "$CMakelists" "$MAKEFILE"; do
  [[ -f "$required" ]] || { echo "[sync_and_build] missing: $required" >&2; exit 1; }
done
cp -f "$IPC_SRC" "$IPC_DST"
cp -f "$HDR_SRC" "$HDR_DST"
cp -f "$IPC_HDR_SRC" "$IPC_HDR_DST"

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

# Refresh our managed registration when its schema changes, as well as on
# initial injection. Refuse to rewrite an unrecognised, manually added tool.
if grep -q '"approach_alert"' "$REGISTRY"; then
  if ! grep -q 'Contest 313 edge_walker: approach alert tool' "$REGISTRY"; then
    echo '[sync_and_build] FAIL: unmanaged approach_alert registration' >&2
    exit 1
  fi
  sed -i '/\/\* Contest 313 edge_walker: approach alert tool/,/tool_approach_alert_execute);/d' "$REGISTRY"
fi
sed -i '/tool_launch_quickapp_execute/r '"$EW/ai_agent_ext/patch_tool_registry.snip" "$REGISTRY"

# sed succeeds even when its insertion anchor is absent. Reject incomplete
# injection before compiling, and retain hashes for reproducibility.
verify_patch() {
  if ! grep -Fq "$1" "$2"; then
    echo "[sync_and_build] FAIL: missing $1 in $2 (check injection anchors)" >&2
    exit 1
  fi
}
verify_patch 'src/tools/tool_approach_alert_ipc.c' "$CMakelists"
verify_patch 'src/tools/tool_approach_alert_ipc.c' "$MAKEFILE"
verify_patch '#include "tools/tool_approach_alert.h"' "$REGISTRY"
verify_patch '"approach_alert"' "$REGISTRY"
verify_patch 'tool_approach_alert_execute);' "$REGISTRY"
verify_patch 'TOOL_PARAM_STR("event_id"' "$REGISTRY"
mkdir -p "$BUILD_DIR"
sha256sum "$IPC_DST" "$HDR_DST" "$IPC_HDR_DST" "$REGISTRY" "$CMakelists" "$MAKEFILE" | tee "$STAMP"
echo "[sync_and_build] verified approach_alert sources and registry (local ew dispatch is separate)"

# Allows injection verification without a cross compiler or firmware build.
if [[ "${EW_PATCH_ONLY:-0}" == "1" ]]; then
  exit 0
fi

DMA_PATCH="$CONTEST/board_overlay/sf32lb52_devkit_lcd/patches/wifi_uart_dma.patch"
if ! git -C "$OPENVELA/vendor/sifli" apply --reverse --check "$DMA_PATCH" >/dev/null 2>&1; then
  git -C "$OPENVELA/vendor/sifli" apply --check "$DMA_PATCH"
  git -C "$OPENVELA/vendor/sifli" apply "$DMA_PATCH"
fi

configure_board() {
  cmake -B "$BUILD_DIR" -S "$OPENVELA/nuttx" -GNinja \
    -DBOARD_CONFIG="$BOARD_CFG" \
    -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations"
}
echo "[sync_and_build] cmake configure..."
configure_board

# The stock ai_agent preset predates the ESP UART3 wiring. Preserve its local
# choices, then expand just the required application and peripheral settings.
REQUIRED_CONFIG=(
  CONFIG_EXAMPLES_AI_AGENT_VELA=y
  CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y
  CONFIG_BSP_USING_UART3=y
  CONFIG_BSP_UART3_RX_USING_DMA=y
)
CONFIG_CHANGED=0
for setting in "${REQUIRED_CONFIG[@]}"; do
  if ! grep -qxF "$setting" "$BUILD_DIR/.config"; then
    if [[ ! -f "$BUILD_DIR/.ew_ai_config_before" ]]; then
      cp "$BUILD_DIR/.config" "$BUILD_DIR/.ew_ai_config_before"
    fi
    key="${setting%%=*}"
    sed -i "/^${key}=/d; /^# ${key} is not set$/d" "$BUILD_DIR/.config"
    echo "$setting" >> "$BUILD_DIR/.config"
    CONFIG_CHANGED=1
  fi
  key="${setting%%=*}"
  # A previous run may have stopped after editing .config but before
  # regenerating its header. Detect that state on every invocation.
  if ! grep -Eq "^#define[[:space:]]+${key}[[:space:]]+1([[:space:]]|$)" \
       "$BUILD_DIR/include/nuttx/config.h" 2>/dev/null; then
    CONFIG_CHANGED=1
  fi
done
if [[ "$CONFIG_CHANGED" == 1 ]]; then
  (cd "$OPENVELA/nuttx" && env KCONFIG_CONFIG="$BUILD_DIR/.config" \
    EXTERNALDIR=dummy APPSDIR="$OPENVELA/apps" DRIVERS_PLATFORM_DIR=dummy \
    APPSBINDIR="$BUILD_DIR/apps" BINDIR="$BUILD_DIR" olddefconfig)
  cmake -E remove -f "$BUILD_DIR/include/nuttx/config.h"
  configure_board
fi
# This NuttX revision creates config.h as a build target, not at configure time.
cmake --build "$BUILD_DIR" --target nuttx_context
for setting in "${REQUIRED_CONFIG[@]}" CONFIG_LV_USE_NUTTX=y; do
  grep -qxF "$setting" "$BUILD_DIR/.config" || {
    echo "[sync_and_build] FAIL: required active config missing: $setting" >&2
    exit 1
  }
  key="${setting%%=*}"
  grep -Eq "^#define[[:space:]]+${key}[[:space:]]+1([[:space:]]|$)" \
    "$BUILD_DIR/include/nuttx/config.h" || {
    echo "[sync_and_build] FAIL: generated config header lacks $key" >&2
    exit 1
  }
done

echo "[sync_and_build] build..."
cmake --build "$BUILD_DIR" -j"${EW_BUILD_JOBS:-$(nproc)}"
[[ -s "$BUILD_DIR/nuttx.bin" ]]

echo "[sync_and_build] OK → $BUILD_DIR/nuttx.bin"
ls -lh "$BUILD_DIR/nuttx.bin"
