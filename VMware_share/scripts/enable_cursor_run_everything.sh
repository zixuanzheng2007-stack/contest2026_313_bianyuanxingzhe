#!/usr/bin/env bash
# 启用 Cursor Agent「Run Everything」+ 关闭三项保护（竞赛编译机专用）
# 用法: bash scripts/enable_cursor_run_everything.sh
# 注意: 需先完全退出 Cursor，或在脚本提示时确认关闭后重开。
set -euo pipefail

DB="${CURSOR_STATE_DB:-$HOME/.config/Cursor/User/globalStorage/state.vscdb}"
KEY='src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser'
CLI_CFG="$HOME/.cursor/cli-config.json"

if pgrep -f '/usr/share/cursor/cursor' >/dev/null 2>&1; then
  echo "检测到 Cursor 正在运行，内存状态会覆盖数据库修改。"
  echo "请先完全退出 Cursor（所有窗口），然后重新运行本脚本。"
  echo "或在本对话输入 /run-everything on 后 Reload Window（若版本支持）。"
  exit 1
fi

test -f "$DB" || { echo "找不到 $DB"; exit 1; }

cp -a "$DB" "${DB}.bak.$(date +%Y%m%d%H%M%S)"

python3 <<PY
import sqlite3, json
from pathlib import Path
db = Path("$DB")
key = "$KEY"
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute('SELECT value FROM ItemTable WHERE key=?', (key,))
row = cur.fetchone()
if not row:
    raise SystemExit('applicationUser 键不存在')
v = json.loads(row[0])
cs = v.setdefault('composerState', {})
cs['yoloEnableRunEverything'] = True
cs['yoloDeleteFileDisabled'] = True
cs['yoloOutsideWorkspaceDisabled'] = True
cs['playwrightProtection'] = False
cs['enableSmartAuto'] = False
cs['doNotShowFullYoloModeWarningAgain'] = True
cs['doNotShowYoloModeWarningAgain'] = True
v['composerState'] = cs
cur.execute('UPDATE ItemTable SET value=? WHERE key=?', (json.dumps(v, separators=(',', ':')), key))
cur.execute('SELECT value FROM ItemTable WHERE key=?', ('adminSettings.cached',))
row = cur.fetchone()
if row:
    admin = json.loads(row[0])
    arc = admin.setdefault('autoRunControls', {})
    arc['enableRunEverything'] = True
    arc['deleteFileProtection'] = False
    arc['browserProtection'] = False
    arc['enableAllowlistMode'] = False
    arc['enableSmartAuto'] = False
    admin['autoRunControls'] = arc
    cur.execute('UPDATE ItemTable SET value=? WHERE key=?', (json.dumps(admin, separators=(',', ':')), 'adminSettings.cached'))
con.commit()
con.close()
print('state.vscdb 已写入 Run Everything')
PY

mkdir -p "$(dirname "$CLI_CFG")"
cat > "$CLI_CFG" <<'JSON'
{
  "version": 1,
  "permissions": {
    "allow": ["Shell(**)", "Mcp(**)", "WebFetch(**)", "WebSearch(**)"],
    "deny": []
  },
  "approvalMode": "unrestricted",
  "sandbox": {
    "mode": "disabled"
  }
}
JSON
echo "CLI 配置 -> $CLI_CFG"
echo "完成。请重新启动 Cursor。"
