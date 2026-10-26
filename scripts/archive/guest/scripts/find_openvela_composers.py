#!/usr/bin/env python3
import json
import os
import sqlite3
from pathlib import Path

db = Path(os.environ["APPDATA"]) / "Cursor/User/globalStorage/state.vscdb"
conn = sqlite3.connect(str(db))
conn.execute("PRAGMA query_only=ON")
row = conn.execute(
    "SELECT value FROM ItemTable WHERE key='composer.composerHeaders'"
).fetchone()
data = json.loads(row[0])
all_c = data.get("allComposers") or []
print("allComposers:", len(all_c))
found = 0
for comp in all_c:
    wid = comp.get("workspaceIdentifier") or {}
    uri = wid.get("uri") or {}
    fp = uri.get("fsPath") or uri.get("path") or ""
    if "openvela" in fp.lower() or "contest" in fp.lower():
        found += 1
        print("FOUND", comp.get("composerId"), fp)
print("openvela/contest matches:", found)
conn.close()
