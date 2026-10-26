#!/usr/bin/env bash
set -euo pipefail
SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
CONTEST="${CONTEST:-/home/a1/openvela/contest2026_313_bianyuanxingzhe}"

bash "$CONTEST/scripts/stop_guest_bus_loop.sh" 2>/dev/null || true

WAKE_PID="$SHARE/mailbox/status/guest_wake_tail.pid"
if [[ -f "$WAKE_PID" ]]; then
  pid="$(cat "$WAKE_PID")"
  kill "$pid" 2>/dev/null && echo "stopped wake_tail pid=$pid" || echo "wake_tail stale"
  rm -f "$WAKE_PID"
fi

date '+%Y-%m-%d %H:%M:%S guest_monitor OFF' >"$SHARE/mailbox/status/GUEST_WATCH.txt"
echo "guest monitor stopped"
