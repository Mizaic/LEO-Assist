"""
Summarise the audit SQLite database: schema, counts, sample rows.
"""

import sqlite3, json, sys
from pathlib import Path

DB = Path("scripts/investigations/encounter_audit/encounter_audit.db")

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables:
    if t == "sqlite_sequence":
        continue
    cur.execute(f"SELECT COUNT(*) FROM {t}")  # noqa: S608
    cnt = cur.fetchone()[0]
    print(f"\n-- {t}: {cnt} rows")
    cur.execute(f"PRAGMA table_info({t})")  # noqa: S608
    cols = [r["name"] for r in cur.fetchall()]
    print(f"   columns: {cols}")
    cur.execute(f"SELECT * FROM {t} LIMIT 3")  # noqa: S608
    for row in cur.fetchall():
        d = dict(row)
        # truncate llm_response for display
        for k in list(d.keys()):
            if isinstance(d[k], str) and len(d[k]) > 200:
                d[k] = d[k][:200] + "..."
        print(f"   {d}")

conn.close()
