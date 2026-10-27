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

SOURCE_INPUT_SHA=$($PYTHON "$CONTEST/scripts/host/firmware_provenance.py" digest --root "$CONTEST")
# Refuse to mutate a shared SDK or silently reuse an old build directory.
[[ -n "${ISOLATION_MANIFEST:-}" ]] || { echo 'FAIL: ISOLATION_MANIFEST from the private build is required.' >&2; exit 2; }
"$PYTHON" - "$ISOLATION_MANIFEST" "$OPENVELA" "$SOURCE_INPUT_SHA" <<'PY'
import json,sys
from pathlib import Path
proof=json.loads(Path(sys.argv[1]).read_text())
assert Path(proof['private_workspace']).resolve()==Path(sys.argv[2]).resolve(), 'Not the private workspace'
assert proof['source_tree_sha256']==sys.argv[3], 'Isolation evidence does not match source inputs'
assert proof.get('board_tested') is False, 'Invalid isolation evidence'
PY
echo "[stage3] build main firmware"
OPENVELA="$OPENVELA" CONTEST="$CONTEST" bash "$CONTEST/scripts/guest/build_ew_main.sh"
"$PYTHON" "$CONTEST/scripts/host/firmware_provenance.py" record --root "$CONTEST" \
  --build-dir "$MAIN_BUILD_DIR" --expected "$SOURCE_INPUT_SHA"

args=(
  seal
  --version "$VERSION"
  --main-build-dir "$MAIN_BUILD_DIR"
  --rollback-bin "$ROLLBACK_BIN"
  --output "$OUTPUT"
)

if [[ "$WITH_AGENT" == "1" ]]; then
  echo "[stage3] build independent ai_agent firmware"
  (cd "$CONTEST/app/edge_walker" && OPENVELA="$OPENVELA" CONTEST="$CONTEST" bash sync_and_build.sh)
  "$PYTHON" "$CONTEST/scripts/host/firmware_provenance.py" record --root "$CONTEST" \
    --build-dir "$AGENT_BUILD_DIR" --expected "$SOURCE_INPUT_SHA"
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
