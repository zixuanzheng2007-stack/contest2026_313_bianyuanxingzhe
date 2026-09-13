#!/bin/bash
# 轮询 VMware hgfs mailbox（hgfs 通常没有 inotify）。仅在指纹变化时打印唤醒行。
set -euo pipefail
MAIL="${MAILBOX:-/home/a1/VMware_share/mailbox}"
STATE="${STATE:-$HOME/.cache/ew_mailbox_fp.txt}"
INTERVAL="${INTERVAL:-12}"
mkdir -p "$(dirname "$STATE")"

fp() {
  find "$MAIL" -type f \( -name '*.md' -o -name '*.txt' -o -name '*.json' \) \
    ! -name 'host_watch_fp.txt' ! -name 'HOST_WATCH.txt' \
    -printf '%P %s %T@\n' 2>/dev/null | sort | sha256sum | awk '{print $1}'
}

cur="$(fp)"
echo "$cur" > "$STATE"
echo "mailbox_watch init fp=$cur interval=${INTERVAL}s dir=$MAIL"

while true; do
  sleep "$INTERVAL"
  n="$(fp)"
  o="$(cat "$STATE" 2>/dev/null || true)"
  if [ -n "$n" ] && [ "$n" != "$o" ]; then
    echo "$n" > "$STATE"
    newest="$(find "$MAIL" -type f \( -name '*.md' -o -name '*.txt' -o -name '*.json' \) \
      ! -name 'host_watch_fp.txt' ! -name 'HOST_WATCH.txt' \
      -printf '%T@ %P\n' 2>/dev/null | sort -nr | head -5 | awk '{print $2}' | tr '\n' ' ')"
    echo "AGENT_LOOP_WAKE_mailbox {\"prompt\":\"mailbox changed newest=${newest}; read CURRENT.json and new REPLY/TASK; summarize; do not grab CH343.\"}"
  fi
done
