"""Sample the audit SQLite DB to understand result_json structure."""
import sqlite3
import json
from pathlib import Path

DB = Path("scripts/investigations/encounter_audit/encounter_audit.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== OVERCODED SAMPLES ===")
cur.execute(
    "SELECT encounter_id, result_json FROM encounters"
    " WHERE status='done' LIMIT 10000"
)
shown_oc = 0
shown_miss = 0
shown_wa = 0
rows = cur.fetchall()
for row in rows:
    d = json.loads(row["result_json"])
    oc = d.get("overcoded", [])
    ms = [m for m in d.get("missing", []) if m.get("severity") == "critical"]
    wa = d.get("wrong_assertion", [])
    if oc and shown_oc < 3:
        print(f"encounter: {row['encounter_id']}")
        print(f"  overcoded: {json.dumps(oc[:2], indent=2)}")
        shown_oc += 1
        print()

print("=== CRITICAL MISSING SAMPLES ===")
for row in rows:
    d = json.loads(row["result_json"])
    ms = [m for m in d.get("missing", []) if m.get("severity") == "critical"]
    if ms and shown_miss < 3:
        print(f"encounter: {row['encounter_id']}")
        print(f"  missing: {json.dumps(ms[:2], indent=2)}")
        shown_miss += 1
        print()

print("=== WRONG ASSERTION SAMPLES ===")
for row in rows:
    d = json.loads(row["result_json"])
    wa = d.get("wrong_assertion", [])
    if wa and shown_wa < 3:
        print(f"encounter: {row['encounter_id']}")
        print(f"  wrong_assertion: {json.dumps(wa[:2], indent=2)}")
        shown_wa += 1
        print()

conn.close()
