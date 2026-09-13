#!/usr/bin/env bash
set -euo pipefail
SHARE="${SHARE:-/mnt/hgfs/VMware_share}"
PIDFILE="$SHARE/mailbox/status/guest_bus_loop.pid"
if [[ ! -f "$PIDFILE" ]]; then
  echo "not running (no pid file)"
  exit 0
fi
pid="$(cat "$PIDFILE")"
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "stopped pid=$pid"
else
  echo "stale pid=$pid"
fi
rm -f "$PIDFILE"
date '+%Y-%m-%d %H:%M:%S guest mailbox_bus_loop OFF' \
  >"$SHARE/mailbox/status/GUEST_WATCH.txt"
