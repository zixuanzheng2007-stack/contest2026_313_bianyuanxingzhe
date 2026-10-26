#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db = Path.home() / ".config/Cursor/User/globalStorage/state.vscdb"
if not db.exists():
    db = Path.home() / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb"
print("db:", db, "exists:", db.exists())
if not db.exists():
    raise SystemExit(1)
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
if "cursorDiskKV" in tables:
    n = cur.execute("SELECT COUNT(*) FROM cursorDiskKV").fetchone()[0]
    nc = cur.execute("SELECT COUNT(*) FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchone()[0]
    nb = cur.execute("SELECT COUNT(*) FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'").fetchone()[0]
    print("cursorDiskKV:", n, "composerData:", nc, "bubbleId:", nb)
if "ItemTable" in tables:
    keys = [r[0] for r in cur.execute("SELECT key FROM ItemTable LIMIT 15")]
    print("ItemTable sample:", keys)
conn.close()
