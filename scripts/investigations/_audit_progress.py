"""Check audit re-run progress and estimate ETA."""

import sqlite3
import os
from datetime import datetime, timedelta

DB = "scripts/investigations/encounter_audit/encounter_audit.db"
TOTAL = 30783
STARTED = datetime(2026, 4, 4, 18, 4, 36)

if not os.path.exists(DB):
    print("Audit DB not found - still in early phase")
else:
    db = sqlite3.connect(DB)
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", [t[0] for t in tables])
    for (t_name,) in tables:
        n = db.execute(f"SELECT COUNT(*) FROM {t_name}").fetchone()[0]
        print(f"  {t_name}: {n:,} rows")

    if tables:
        t_name = tables[0][0]
        done = db.execute(
            f"SELECT COUNT(DISTINCT encounter_id) FROM {t_name}"
        ).fetchone()[0]
        now = datetime.now()
        elapsed = (now - STARTED).total_seconds() / 3600
        pct = done / TOTAL * 100
        print(f"\nProgress: {done:,} / {TOTAL:,}  ({pct:.1f}%)")
        print(f"Elapsed : {elapsed:.1f}h")
        if done > 0:
            rate = done / elapsed
            remaining_h = (TOTAL - done) / rate
            eta = now + timedelta(hours=remaining_h)
            print(f"Rate    : {rate:.0f} enc/h")
            print(f"ETA     : {eta.strftime('%H:%M')} (~{remaining_h:.1f}h left)")
    db.close()
