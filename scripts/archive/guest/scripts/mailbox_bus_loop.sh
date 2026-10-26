#!/usr/bin/env bash
# Guest mailbox 总线：轮询共享盘 → 自动执行 guest 任务 → AGENT_LOOP_WAKE 唤醒本机 Cursor
set -euo pipefail

SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
MAIL="$SHARE/mailbox"
FP="$MAIL/status/guest_watch_fp.txt"
LOG="$MAIL/status/GUEST_EXEC.log"
EXEC="${EXEC:-$SHARE/scripts/mailbox_exec_guest.sh}"
INTERVAL="${INTERVAL:-8}"
PENDING_GUEST_SEC="${PENDING_GUEST_SEC:-120}"
NO_AUTO_EXEC="${NO_AUTO_EXEC:-0}"

last_wake_state=""
pending_elapsed=0

watch_files() {
  local f
  for f in \
    "$MAIL/CURRENT.json" \
    "$SHARE/FROM_HOST_Windows.txt" \
    "$SHARE/FROM_GUEST_Ubuntu.txt" \
    "$MAIL/guest_to_host/HOST_PLEASE_READ.txt"; do
    [[ -f "$f" ]] && echo "$f"
  done
  find "$MAIL/host_to_guest" -maxdepth 1 -type f \
    \( -name 'TASK_*.md' -o -name 'REPLY_*.md' \) 2>/dev/null || true
}

fingerprint() {
  watch_files | sort -u | while read -r p; do
    if [[ -f "$p" ]]; then
      if [[ "$p" == *.bin ]]; then
        printf '%s|%s\n' "${p#"$SHARE/"}" "$(stat -c%s "$p" 2>/dev/null || echo 0)"
      else
        printf '%s|%s|%s\n' "${p#"$SHARE/"}" "$(stat -c%s "$p" 2>/dev/null || echo 0)" \
          "$(sha256sum "$p" 2>/dev/null | awk '{print $1}')"
      fi
    fi
  done | sha256sum | awk '{print $1}'
}

current_field() {
  python3 - "$MAIL/CURRENT.json" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        o = json.load(f)
    cur = o
    for part in sys.argv[2].split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    print("" if cur is None else cur)
except Exception:
    print("")
PY
}

wake_state() {
  printf '%s|%s|%s' \
    "$(current_field owner)" \
    "$(current_field blocker)" \
    "$(current_field active_id)"
}

emit_wake() {
  local reason="$1" exec_json="${2:-{}}"
  local owner blocker active newest prompt payload
  owner="$(current_field owner)"
  blocker="$(current_field blocker)"
  active="$(current_field active_id)"
  newest=$(find "$MAIL" -type f \( -name 'TASK_*.md' -o -name 'REPLY_*.md' -o -name 'CURRENT.json' \) \
    -printf '%T@ %P\n' 2>/dev/null | sort -nr | head -5 | awk '{print $2}' | tr '\n' ' ')

  prompt="Guest mailbox bus AUTO: Read /mnt/hgfs/VMware_share/mailbox/CURRENT.json and AGENT_BUS.md. \
If owner=guest: run mailbox_exec_guest actions or execute active TASK in host_to_guest (build/verify/reply). \
If owner=host: summarize only; do NOT grab CH343/COM7. Honor do_not. \
Latest files: ${newest}. Exec: ${exec_json}"

  payload=$(python3 - <<PY
import json
print(json.dumps({
  "prompt": """$prompt""",
  "reason": "$reason",
  "owner": "$owner",
  "blocker": "$blocker",
  "active": "$active",
  "newest": """$newest""",
}, ensure_ascii=False))
PY
)
  echo "AGENT_LOOP_WAKE_guestbus $payload"
}

run_exec() {
  if [[ "$NO_AUTO_EXEC" == "1" || ! -x "$EXEC" ]]; then
    echo '{"action":"skip"}'
    return 0
  fi
  SHARE="$SHARE" bash "$EXEC" 2>&1 | tail -1
}

handle_tick() {
  local reason="$1" allow_dup="${2:-0}" state exec_out
  state="$(wake_state)"
  if [[ "$allow_dup" != "1" && "$reason" == "pending_guest_task" && "$state" == "$last_wake_state" ]]; then
    return 0
  fi
  last_wake_state="$state"
  exec_out="$(run_exec)"
  emit_wake "$reason" "$exec_out"
  echo "$(date '+%Y-%m-%d %H:%M:%S') tick $state exec=$exec_out" >>"$LOG"
}

mkdir -p "$(dirname "$FP")" "$(dirname "$LOG")"
fp="$(fingerprint)"
echo "$fp" >"$FP"
echo "mailbox_bus_loop guest init fp=$fp interval=${INTERVAL}s autoExec=$((1-NO_AUTO_EXEC)) share=$SHARE"

while true; do
  sleep "$INTERVAL"
  n="$(fingerprint)"
  o="$(cat "$FP" 2>/dev/null || true)"
  if [[ -n "$n" && "$n" != "$o" ]]; then
    echo "$n" >"$FP"
    handle_tick "fingerprint_changed" 1
    pending_elapsed=0
    continue
  fi

  owner="$(current_field owner)"
  if [[ "$owner" == "guest" ]]; then
    pending_elapsed=$((pending_elapsed + INTERVAL))
    if [[ "$pending_elapsed" -ge "$PENDING_GUEST_SEC" ]]; then
      handle_tick "pending_guest_task" 0
      pending_elapsed=0
    fi
  else
    pending_elapsed=0
  fi
done
