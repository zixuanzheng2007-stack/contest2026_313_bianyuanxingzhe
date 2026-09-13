#!/usr/bin/env bash
# 后台启动 Guest mailbox 动态监测（供 Cursor notify_on_output 捕获 AGENT_LOOP_WAKE_guestbus）
set -euo pipefail

SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
LOOP="$SHARE/scripts/mailbox_bus_loop.sh"
PIDFILE="$SHARE/mailbox/status/guest_bus_loop.pid"
INTERVAL="${INTERVAL:-8}"

if [[ ! -d "$SHARE/mailbox" ]]; then
  echo "ERROR: share not mounted at $SHARE"
  echo "  guest: /mnt/hgfs/VMware_share"
  exit 1
fi

if [[ ! -x "$LOOP" ]]; then
  chmod +x "$LOOP" "$SHARE/scripts/mailbox_exec_guest.sh" "$SHARE/scripts/stop_guest_bus_loop.sh"
fi

mkdir -p "$SHARE/mailbox/status"

if [[ -f "$PIDFILE" ]]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
    echo "already running pid=$old"
    echo "stop: bash $(dirname "$0")/stop_guest_bus_loop.sh"
    exit 0
  fi
fi

nohup env SHARE="$SHARE" INTERVAL="$INTERVAL" bash "$LOOP" \
  >>"$SHARE/mailbox/status/guest_bus_loop.out" 2>&1 &
pid=$!
echo "$pid" >"$PIDFILE"
date '+%Y-%m-%d %H:%M:%S guest mailbox_bus_loop ON pid='"$pid" \
  >"$SHARE/mailbox/status/GUEST_WATCH.txt"

echo "guest_bus_loop pid=$pid interval=${INTERVAL}s"
echo "out: $SHARE/mailbox/status/guest_bus_loop.out"
echo "log: $SHARE/mailbox/status/GUEST_EXEC.log"
echo "stop: bash $(dirname "$0")/stop_guest_bus_loop.sh"
