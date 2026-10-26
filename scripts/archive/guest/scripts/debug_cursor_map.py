#!/usr/bin/env python3
import json
import os
import sqlite3
from pathlib import Path

if os.name == "nt":
    db = Path(os.environ["APPDATA"]) / "Cursor/User/globalStorage/state.vscdb"
else:
    db = Path.home() / ".config/Cursor/User/globalStorage/state.vscdb"
print("db:", db)
conn = sqlite3.connect(str(db), check_same_thread=False)
conn.execute("PRAGMA query_only=ON")
cur = conn.cursor()

headers_item = cur.execute(
    "SELECT value FROM ItemTable WHERE key='composer.composerHeaders'"
).fetchone()
print("ItemTable composer.composerHeaders:", "yes" if headers_item else "no")

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
if "composerHeaders" in tables:
    n = cur.execute("SELECT COUNT(*) FROM composerHeaders").fetchone()[0]
    print("composerHeaders table count:", n)

ws_root = db.parent.parent / "workspaceStorage"
for ws in sorted(ws_root.iterdir()):
    wj = ws / "workspace.json"
    if not wj.exists():
        continue
    text = wj.read_text(encoding="utf-8")
    if "contest2026" in text or "openvela" in text.lower():
        print("workspace:", ws.name, text[:180])
        wsdb = ws / "state.vscdb"
        if wsdb.exists():
            wconn = sqlite3.connect(str(wsdb))
            wconn.execute("PRAGMA query_only=ON")
            row = wconn.execute(
                "SELECT value FROM ItemTable WHERE key='composer.composerData'"
            ).fetchone()
            if row:
                try:
                    data = json.loads(row[0])
                    ac = data.get("allComposers") or []
                    print("  workspace composer.composerData allComposers:", len(ac))
                except Exception as e:
                    print("  parse err", e)
            else:
                print("  no composer.composerData in workspace db")
            wconn.close()

conn.close()
