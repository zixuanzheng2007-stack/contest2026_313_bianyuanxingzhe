#!/usr/bin/env bash
# Build main/optional Agent images, then seal a versioned delivery package.
set -euo pipefail

OPENVELA="${OPENVELA:-$HOME/openvela}"
CONTEST="${CONTEST:-$OPENVELA/contest2026_313_bianyuanxingzhe}"
WITH_AGENT="${WITH_AGENT:-1}"
ROLLBACK_BIN="${ROLLBACK_BIN:-}"
APK="${APK:-}"
PYTHON="${PYTHON:-}"
VERSION="${VERSION:-ew-final-$(date +%Y%m%d-%H%M%S)-$(git -C "$CONTEST" rev-parse --short HEAD)}"
OUTPUT="${OUTPUT:-$CONTEST/output/stage3}"
MAIN_BUILD_DIR="$OPENVELA/cmake_out/sf32lb52_devkit_lcd"
AGENT_BUILD_DIR="$OPENVELA/cmake_out/sf32lb52_devkit_lcd_ai_agent"

[[ -n "$ROLLBACK_BIN" && -f "$ROLLBACK_BIN" ]] || {
  echo "FAIL: set ROLLBACK_BIN to a known-good main nuttx.bin." >&2
  exit 2
}
if [[ -z "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || command -v python || true)"
fi
[[ -n "$PYTHON" ]] || { echo "FAIL: python3 is required." >&2; exit 2; }

echo "[stage3] build main firmware"
bash "$CONTEST/scripts/guest/build_ew_main.sh"

args=(
  seal
  --version "$VERSION"
  --main-build-dir "$MAIN_BUILD_DIR"
  --rollback-bin "$ROLLBACK_BIN"
  --output "$OUTPUT"
)

if [[ "$WITH_AGENT" == "1" ]]; then
  echo "[stage3] build independent ai_agent firmware"
  (cd "$CONTEST/app/edge_walker" && bash sync_and_build.sh)
  args+=(--agent-build-dir "$AGENT_BUILD_DIR")
fi
if [[ -n "$APK" ]]; then
  [[ -f "$APK" ]] || { echo "FAIL: APK not found: $APK" >&2; exit 2; }
  args+=(--apk "$APK")
fi

echo "[stage3] seal delivery $VERSION"
"$PYTHON" "$CONTEST/scripts/host/stage3_delivery.py" "${args[@]}"
echo "[stage3] verify portable ZIP"
"$PYTHON" "$CONTEST/scripts/host/stage3_delivery.py" verify \
  --package "$OUTPUT/$VERSION.zip"
echo "[stage3] physical acceptance remains PENDING until the board is tested."
