#!/bin/bash
# 拿 TASK_016 验收过的那版文件跟当前编译树逐行比，确认预警核心没被动过。
M=/mnt/hgfs/VMware_share/mailbox/host_to_guest
APP=~/openvela/contest2026_313_bianyuanxingzhe/app/edge_walker

check() {
  local old="$1" new="$2" name="$3"
  if [ ! -f "$old" ]; then
    echo "[skip] $name (no TASK_016 copy)"
    return
  fi
  if diff -q <(tr -d '\r' < "$old") <(tr -d '\r' < "$new") >/dev/null; then
    echo "[same] $name"
  else
    echo "[diff] $name"
    diff <(tr -d '\r' < "$old") <(tr -d '\r' < "$new") | head -40
  fi
}

check "$M/task016_ew_ld2451.c"   "$APP/ew_ld2451.c"   "ew_ld2451.c  (雷达解析 + alarm 位)"
check "$M/task016_ew_ld2451.h"   "$APP/ew_ld2451.h"   "ew_ld2451.h"
check "$M/task016_alert_buzzer.c" "$APP/alert_buzzer.c" "alert_buzzer.c (后台连续鸣叫)"
check "$M/task016_host_smoke.c"  "$APP/host_smoke.c"  "host_smoke.c (预警回归用例)"
