#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[2].parent / ".claude/skills/contest-log-collector/adapters/cursor"
if not ADAPTER.is_dir():
    ADAPTER = Path.home() / "openvela/.claude/skills/contest-log-collector/adapters/cursor"
sys.path.insert(0, str(ADAPTER))
import backfill_cursor as bc  # noqa: E402

if os.name == "nt":
    dest = Path(r"e:/openvela/contest2026_313_bianyuanxingzhe")
else:
    dest = Path.home() / "openvela/contest2026_313_bianyuanxingzhe"

global_db, ws_dbs = bc.find_cursor_dbs()
print("global_db:", global_db)
print("ws_dbs:", len(ws_dbs))
conn = bc.open_db_readonly(global_db)
mapping = bc.collect_composer_workspace_map(conn, ws_dbs)
conn.close()
print("total composers:", len(mapping))
for cid, path in list(mapping.items())[:15]:
    print(f"  {cid[:24]} -> {path}")
wr = bc._find_workspace_root(dest)
print("workspace_root:", wr)
if wr:
    ws = str(wr.resolve())
    matched = {
        cid: p
        for cid, p in mapping.items()
        if str(Path(p).resolve()).startswith(ws)
    }
    print("matched:", len(matched))
    for cid, p in list(matched.items())[:10]:
        print(f"  MATCH {cid[:24]} -> {p}")
