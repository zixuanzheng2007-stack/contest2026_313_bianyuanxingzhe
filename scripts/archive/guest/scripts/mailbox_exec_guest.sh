#!/usr/bin/env bash
# Guest：读 CURRENT.json，自动执行可脚本化任务（编译、烧录、写回执）
set -euo pipefail

SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
MAIL="$SHARE/mailbox"
CURRENT="$MAIL/CURRENT.json"
LOG="$MAIL/status/GUEST_EXEC.log"
CONTEST="${CONTEST:-/home/a1/openvela/contest2026_313_bianyuanxingzhe}"
AGENT_BUILD_SH="${AGENT_BUILD_SH:-$SHARE/scripts/run_ew_agent_build.sh}"
WIFIUI_BUILD_SH="${WIFIUI_BUILD_SH:-$SHARE/scripts/run_ew_wifiui_build.sh}"
SFTool="${SFTool:-/home/a1/bin/sftool}"
AI_BIN="/home/a1/openvela/cmake_out/sf32lb52_devkit_lcd_ai_agent/nuttx.bin"

log() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  mkdir -p "$(dirname "$LOG")"
  echo "$line" | tee -a "$LOG"
}

json_field() {
  python3 - "$CURRENT" "$1" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8-sig") as f:
        o = json.load(f)
    cur = o
    for part in key.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = None
            break
    print("" if cur is None else cur)
except Exception:
    print("")
PY
}

update_current() {
  python3 - "$CURRENT" "$@" <<'PY'
import json, sys, datetime
path = sys.argv[1]
patch = json.loads(sys.argv[2])
with open(path, encoding="utf-8-sig") as f:
    o = json.load(f)
def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
merge(o, patch)
o["ts"] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds")
with open(path, "w", encoding="utf-8") as f:
    json.dump(o, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

write_reply() {
  local kind="$1" id="$2" ok="$3" detail="$4" script="$5"
  local num="${id#TASK_}"
  local reply="$MAIL/guest_to_host/REPLY_${num}_${kind}.md"
  mkdir -p "$(dirname "$reply")"
  cat >"$reply" <<EOF
# REPLY_${num}_${kind} · Guest 自动执行

| 项 | 值 |
|----|-----|
| 时间 | $(date '+%Y-%m-%d %H:%M') |
| 脚本 | \`${script}\` |
| 结果 | ${ok} |
| 说明 | ${detail} |

自动执行：\`mailbox_exec_guest.sh\`
EOF
  log "wrote $reply"
}

guest_build_ai_agent() {
  local id artifact logf bytes
  id="$(json_field active_id)"
  artifact="artifacts/nuttx_ai_agent.bin"
  logf="/tmp/ew_agent_build.log"

  log "guest_build_ai_agent start active=$id"
  if [[ ! -f "$AGENT_BUILD_SH" ]]; then
    write_reply "BUILD" "$id" "**FAIL**" "missing run_ew_agent_build.sh" "run_ew_agent_build.sh"
    return 1
  fi
  if ! tr -d '\r' < "$AGENT_BUILD_SH" | bash >"$logf" 2>&1; then
    cp -f "$logf" "$SHARE/artifacts/guest_build_fail.log" 2>/dev/null || true
    write_reply "BUILD" "$id" "**FAIL**" "see artifacts/guest_build_fail.log" "run_ew_agent_build.sh"
    return 1
  fi
  if [[ ! -f "$AI_BIN" ]]; then
    write_reply "BUILD" "$id" "**FAIL**" "ai_agent nuttx.bin missing" "run_ew_agent_build.sh"
    return 1
  fi
  mkdir -p "$SHARE/artifacts"
  cp -f "$AI_BIN" "$SHARE/$artifact"
  bytes=$(stat -c%s "$SHARE/$artifact")
  log "guest_build_ai_agent ok → $artifact ($bytes B)"

  update_current "$(python3 - <<PY
import json
print(json.dumps({
  "flash": {"bin": "$artifact", "port": "COM7", "ok": False, "addr": "0x12010000", "bytes": $bytes},
  "blocker": "host_flash",
  "owner": "host",
  "guest": {"doing": "built $artifact", "need": "host flash COM7"},
  "host": {"doing": "await flash", "need": "sftool COM7 or hand CH343 to host"}
}, ensure_ascii=False))
PY
)"
  write_reply "BUILD" "$id" "**exit 0**" "$artifact ($bytes B)" "run_ew_agent_build.sh"
  echo "$(date '+%Y-%m-%d %H:%M') guest built $artifact → host flash COM7" >"$SHARE/FROM_GUEST_Ubuntu.txt"
  return 0
}

guest_build_wifiui() {
  local id artifact logf bytes
  id="$(json_field active_id)"
  artifact="artifacts/nuttx_wifiui.bin"
  logf="/tmp/ew_wifiui_build.log"

  log "guest_build_wifiui start active=$id"
  if [[ ! -f "$WIFIUI_BUILD_SH" ]]; then
    write_reply "BUILD" "$id" "**FAIL**" "missing run_ew_wifiui_build.sh" "run_ew_wifiui_build.sh"
    return 1
  fi
  if ! tr -d '\r' < "$WIFIUI_BUILD_SH" | bash >"$logf" 2>&1; then
    cp -f "$logf" "$SHARE/artifacts/guest_wifiui_build_fail.log" 2>/dev/null || true
    write_reply "BUILD" "$id" "**FAIL**" "see artifacts/guest_wifiui_build_fail.log" "run_ew_wifiui_build.sh"
    return 1
  fi
  if [[ ! -f "$SHARE/$artifact" ]]; then
    write_reply "BUILD" "$id" "**FAIL**" "$artifact missing after build" "run_ew_wifiui_build.sh"
    return 1
  fi
  bytes=$(stat -c%s "$SHARE/$artifact")
  cp -f "$logf" "$SHARE/artifacts/guest_wifiui_build_ok.log" 2>/dev/null || true
  log "guest_build_wifiui ok → $artifact ($bytes B)"

  update_current "$(python3 - <<PY
import json
print(json.dumps({
  "flash": {
    "bin": "$artifact", "port": "/dev/ttyACM0", "ok": False,
    "addr": "0x12010000", "bytes": $bytes, "via": "guest_sftool"
  },
  "blocker": "guest_flash",
  "owner": "guest",
  "guest": {"doing": "built $artifact", "need": "auto flash /dev/ttyACM0"},
  "host": {"doing": "await guest flash + screen verify", "need": "WiFi scan/join on device"}
}, ensure_ascii=False))
PY
)"
  write_reply "BUILD" "$id" "**exit 0**" "$artifact ($bytes B) → guest_flash next" "run_ew_wifiui_build.sh"
  echo "$(date '+%Y-%m-%d %H:%M') guest built $artifact → guest_flash ttyACM0" >"$SHARE/FROM_GUEST_Ubuntu.txt"
  return 0
}

guest_flash_device() {
  local id rel port addr bin_path logf
  id="$(json_field active_id)"
  rel="$(json_field flash.bin)"
  port="$(json_field flash.port)"
  addr="$(json_field flash.addr)"
  logf="/tmp/guest_flash.log"

  [[ -z "$rel" ]] && rel="artifacts/nuttx_wifiui.bin"
  [[ -z "$port" || "$port" == COM7* ]] && port="/dev/ttyACM0"
  [[ -z "$addr" ]] && addr="0x12010000"
  bin_path="$SHARE/$rel"

  log "guest_flash start port=$port bin=$bin_path"
  if [[ ! -f "$bin_path" ]]; then
    write_reply "FLASH" "$id" "**FAIL**" "missing $bin_path" "sftool"
    return 1
  fi
  if [[ ! -x "$SFTool" ]]; then
    write_reply "FLASH" "$id" "**FAIL**" "sftool missing $SFTool" "sftool"
    return 1
  fi
  if [[ ! -e "$port" ]]; then
    write_reply "FLASH" "$id" "**FAIL**" "$port not present (USB passthrough?)" "sftool"
    return 1
  fi

  if ! "$SFTool" -c SF32LB52 -p "$port" -b 1000000 \
      --before default_reset --after soft_reset write_flash --verify \
      "${bin_path}@${addr}" >"$logf" 2>&1; then
    cp -f "$logf" "$SHARE/artifacts/guest_flash_fail.log" 2>/dev/null || true
    write_reply "FLASH" "$id" "**FAIL**" "sftool exit non-zero; see guest_flash_fail.log" "sftool"
    update_current '{"blocker":"guest_flash","guest":{"need":"retry flash or reboot board"}}'
    return 1
  fi

  cp -f "$logf" "$SHARE/artifacts/guest_flash_ok.log" 2>/dev/null || true
  local bytes
  bytes=$(stat -c%s "$bin_path")
  log "guest_flash ok $bin_path @ $addr"

  [[ -z "$rel" ]] && rel="artifacts/$(basename "$bin_path")"
  update_current "$(python3 - "$rel" "$port" "$addr" "$bytes" <<'PY'
import json, sys
rel, port, addr, bytes_ = sys.argv[1:5]
print(json.dumps({
  "flash": {"bin": rel, "port": port, "ok": True, "addr": addr, "bytes": int(bytes_), "via": "guest_sftool"},
  "blocker": "screen_verify",
  "owner": "host",
  "guest": {"doing": "flash OK", "need": "none"},
  "host": {"doing": "screen WiFi verify", "need": "scan list + join; report status line text"}
}, ensure_ascii=False))
PY
)"
  write_reply "FLASH" "$id" "**exit 0**" "$(basename "$bin_path") @ $addr via $port" "sftool"
  echo "$(date '+%Y-%m-%d %H:%M') guest flashed $(basename "$bin_path") → host screen_verify" >"$SHARE/FROM_GUEST_Ubuntu.txt"
  return 0
}

main() {
  if [[ ! -f "$CURRENT" ]]; then
    log "no CURRENT.json"
    echo '{"action":"none","reason":"no_current"}'
    exit 0
  fi

  local owner blocker active flash_bin
  owner="$(json_field owner)"
  blocker="$(json_field blocker)"
  active="$(json_field active_id)"
  flash_bin="$(json_field flash.bin)"
  log "tick owner=$owner blocker=$blocker active=$active bin=$flash_bin"

  if [[ "$owner" != "guest" ]]; then
    echo "{\"action\":\"idle\",\"owner\":\"$owner\"}"
    exit 0
  fi

  case "$blocker" in
    guest_build_wifi|guest_build_wifiui)
      if guest_build_wifiui; then
        echo '{"action":"built_wifiui","ok":true}'
        # 链式：同轮继续烧录（若 build 已把 blocker 改为 guest_flash）
        if [[ "$(json_field blocker)" == "guest_flash" ]]; then
          if guest_flash_device; then
            echo '{"action":"built_and_flashed","ok":true}'
          else
            echo '{"action":"built_flash_failed","ok":false}'
          fi
        fi
      else
        echo '{"action":"build_failed","ok":false}'
      fi
      ;;
    guest_build|guest_compile)
      if [[ "$flash_bin" == *wifiui* ]]; then
        guest_build_wifiui || { echo '{"action":"build_failed","ok":false}'; exit 0; }
        if [[ "$(json_field blocker)" == "guest_flash" ]]; then
          guest_flash_device && echo '{"action":"built_and_flashed","ok":true}' || echo '{"action":"flash_failed","ok":false}'
        else
          echo '{"action":"built_wifiui","ok":true}'
        fi
      else
        if guest_build_ai_agent; then
          echo '{"action":"built","ok":true}'
        else
          echo '{"action":"build_failed","ok":false}'
        fi
      fi
      ;;
    guest_flash)
      if guest_flash_device; then
        echo '{"action":"flashed","ok":true}'
      else
        echo '{"action":"flash_failed","ok":false}'
      fi
      ;;
    guest_verify)
      log "guest_verify: wake Cursor for ACM0/NSH checks"
      echo '{"action":"wake_agent","blocker":"guest_verify"}'
      ;;
    *)
      echo "{\"action\":\"wake_agent\",\"owner\":\"guest\",\"blocker\":\"$blocker\",\"active\":\"$active\"}"
      ;;
  esac
}

main "$@"
