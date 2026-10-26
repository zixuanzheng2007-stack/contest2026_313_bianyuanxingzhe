#!/usr/bin/env bash
# 把 guest_bus_loop.out 里的 AGENT_LOOP_WAKE 行转发到 stdout，供 Cursor notify_on_output 捕获
set -euo pipefail
OUT="${OUT:-/mnt/hgfs/VMware_share/mailbox/status/guest_bus_loop.out}"
touch "$OUT"
echo "cursor_wake_tail watching $OUT (pattern AGENT_LOOP_WAKE_guestbus)"
tail -n 0 -F "$OUT" 2>/dev/null | while IFS= read -r line; do
  case "$line" in
    AGENT_LOOP_WAKE_guestbus*)
      echo "$line"
      ;;
  esac
done
