#!/usr/bin/env bash
# Build and publish only a successfully compiled Edge Walker image.
set -euo pipefail

OPENVELA="${OPENVELA:-$HOME/openvela}"
CONTEST="${CONTEST:-$OPENVELA/contest2026_313_bianyuanxingzhe}"
BUILD_DIR="${BUILD_DIR:-$OPENVELA/cmake_out/sf32lb52_devkit_lcd}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/mnt/hgfs/VMware_share/artifacts}"
export PATH="$HOME/bin:$HOME/.local/bin:$OPENVELA/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$OPENVELA/prebuilts/build-tools/linux-x86_64/bin:$PATH"
BOARD="$OPENVELA/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd"
DEF="$BOARD/configs/nsh/defconfig"
SRC="$CONTEST/app/edge_walker"
DEMO="$OPENVELA/packages/demos/contest2026_313_edge_walker"
OVERLAY="$CONTEST/board_overlay/sf32lb52_devkit_lcd"
mkdir -p "$ARTIFACT_DIR"
LOG="$ARTIFACT_DIR/build_ew_main.log"
exec > >(tee "$LOG") 2>&1
trap 'rc=$?; echo "BUILD_FAILED exit=$rc line=$LINENO"; exit "$rc"' ERR
trap 'if [[ -n "${STAGE:-}" ]]; then rm -f "$STAGE/nuttx.bin" "$STAGE/nuttx.bin.sha256" "$STAGE/nuttx.build.txt"; rmdir "$STAGE"; fi' EXIT
STAGE=''
echo "[build_ew_main] $(date -Iseconds) source=$SRC"
cd "$OPENVELA"
[[ -d "$SRC" && -f "$DEF" ]] || { echo 'Missing app or board defconfig'; exit 2; }

# Preserve the independently validated board fixes.
PATCH_SH="$CONTEST/scripts/patches/devkit_lcd_touch_i2c.sh"
if [[ -f "$PATCH_SH" ]]; then
  bash "$PATCH_SH" "$OPENVELA"
fi
DMA_PATCH="$OVERLAY/patches/wifi_uart_dma.patch"
if [[ -f "$DMA_PATCH" ]]; then
  if git -C "$OPENVELA/vendor/sifli" apply --reverse --check "$DMA_PATCH" >/dev/null 2>&1; then
    echo 'wifi UART DMA patch already applied'
  else
    git -C "$OPENVELA/vendor/sifli" apply --check "$DMA_PATCH"
    git -C "$OPENVELA/vendor/sifli" apply "$DMA_PATCH"
  fi
fi
if [[ -f "$OVERLAY/wifi_dma.config" ]]; then
  while IFS= read -r setting || [[ -n "$setting" ]]; do
    setting="${setting%$'\r'}"
    case "$setting" in
      CONFIG_*=y) grep -qxF "$setting" "$DEF" || echo "$setting" >> "$DEF" ;;
    esac
  done < "$OVERLAY/wifi_dma.config"
fi

# Never replace a teammate's real demo directory with a symlink.
mkdir -p "$(dirname "$DEMO")"
if [[ -e "$DEMO" && ! -L "$DEMO" ]]; then
  echo "Refusing to replace existing demo directory: $DEMO"
  exit 2
fi
ln -sfn "$SRC" "$DEMO"
grep -qxF 'CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y' "$DEF" ||
  echo 'CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y' >> "$DEF"

mkdir -p "$BOARD/src/etc/init.d"
if [[ -f "$OVERLAY/etc/init.d/rcS.user" ]]; then
  # rcS is preprocessed as C: omit shell comments.
  sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$OVERLAY/etc/init.d/rcS.user" > "$BOARD/src/etc/init.d/rcS"
else
  printf 'sleep 2\new boot\n' > "$BOARD/src/etc/init.d/rcS"
fi

# Keep the existing build and its local configuration for incremental rebuilds.
cmake -B "$BUILD_DIR" -S "$OPENVELA/nuttx" -GNinja \
  -DBOARD_CONFIG=../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh \
  -DEXTRA_FLAGS='-Wno-cpp -Wno-deprecated-declarations'
grep -qxF 'CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y' "$BUILD_DIR/.config"
if [[ -f "$OVERLAY/wifi_dma.config" ]]; then
  while IFS= read -r setting || [[ -n "$setting" ]]; do
    setting="${setting%$'\r'}"
    case "$setting" in
      CONFIG_*=y)
        if ! grep -qxF "$setting" "$BUILD_DIR/.config"; then
          echo "Existing build config lacks $setting; merge the board overlay before rebuilding."
          exit 3
        fi ;;
    esac
  done < "$OVERLAY/wifi_dma.config"
fi
cmake --build "$BUILD_DIR" -j"${EW_BUILD_JOBS:-$(nproc)}"
[[ -s "$BUILD_DIR/nuttx.bin" ]]
SOURCE_SHA256=$(find "$SRC" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d ' ' -f1)
CONFIG_SHA256=$(sha256sum "$BUILD_DIR/.config" | cut -d ' ' -f1)
if GIT_STATUS=$(git -C "$CONTEST" status --porcelain --untracked-files=no 2>/dev/null); then
  TRACKED_DIRTY=$(if [[ -n "$GIT_STATUS" ]]; then echo yes; else echo no; fi)
else
  TRACKED_DIRTY=unavailable
fi

# Stage on the destination filesystem. Build failures cannot publish stale images.
STAGE="$(mktemp -d "$ARTIFACT_DIR/.ew_release.XXXXXX")"
cp "$BUILD_DIR/nuttx.bin" "$STAGE/nuttx.bin"
(cd "$STAGE" && sha256sum nuttx.bin > nuttx.bin.sha256)
{
  echo "built_at=$(date -Iseconds)"
  echo 'board=sf32lb52_devkit_lcd:nsh'
  echo "commit=$(git -C "$CONTEST" rev-parse HEAD 2>/dev/null || echo unavailable)"
  echo "tracked_dirty=$TRACKED_DIRTY"
  echo "source_sha256=$SOURCE_SHA256"
  echo "config_sha256=$CONFIG_SHA256"
  cat "$STAGE/nuttx.bin.sha256"
} > "$STAGE/nuttx.build.txt"
mv -f "$STAGE/nuttx.bin" "$ARTIFACT_DIR/nuttx.bin"
mv -f "$STAGE/nuttx.bin.sha256" "$ARTIFACT_DIR/nuttx.bin.sha256"
# Metadata is the completion marker; verify its image hash before flashing.
mv -f "$STAGE/nuttx.build.txt" "$ARTIFACT_DIR/nuttx.build.txt"
echo "BUILD_OK $ARTIFACT_DIR/nuttx.bin"
