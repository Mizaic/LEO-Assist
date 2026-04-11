import sqlite3

db = sqlite3.connect("scripts/investigations/encounter_audit/remediation.db")
cur = db.cursor()

for table in ["remediated", "enc_processed"]:
    cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
    print(f"\n{table} columns: {[c[1] for c in cols]}")
    sample = cur.execute(f"SELECT * FROM {table} LIMIT 2").fetchall()
    for r in sample:
        print(" ", r)
db.close()
