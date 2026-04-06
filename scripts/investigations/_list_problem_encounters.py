"""List all encounter IDs from the main audit DB that have problematic assessments.

Outputs:
- Console summary by label
- scripts/investigations/encounter_audit/problem_encounters.jsonl
  (one JSON object per encounter: encounter_id, patient_id, date, assessment, confidence)
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "scripts" / "investigations" / "encounter_audit" / "encounter_audit.db"
OUT_PATH = DB_PATH.parent / "problem_encounters.jsonl"

PROBLEM_LABELS = {
    "has_issues",
    "not_clean",
    "incomplete",
    "needs_review",
    "needs_attention",
    "dirty",
    "issues_found",
    "parse_error",
    "errors_found",
    "partial",
    "overcoded",
}

db = sqlite3.connect(str(DB_PATH))
db.row_factory = sqlite3.Row

rows = db.execute(
    """
    SELECT encounter_id, patient_id, date,
           json_extract(result_json, '$.encounter_assessment') AS assessment,
           json_extract(result_json, '$.confidence') AS confidence,
           json_extract(result_json, '$.notes') AS notes
    FROM encounters
    WHERE status = 'done'
    ORDER BY date
    """
).fetchall()

buckets: dict[str, list] = {}
records: list[dict] = []

for row in rows:
    assess = row["assessment"] or "null"
    if assess in PROBLEM_LABELS:
        entry = {
            "encounter_id": row["encounter_id"],
            "patient_id": row["patient_id"],
            "date": row["date"],
            "assessment": assess,
            "confidence": row["confidence"],
            "notes": row["notes"],
        }
        buckets.setdefault(assess, []).append(entry)
        records.append(entry)

db.close()

print("\n=== Problem encounter counts (main audit DB) ===")
total = 0
for label, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
    total += len(items)
    print(f"  {label:<20} {len(items):>5}")
print(f"  {'TOTAL':<20} {total:>5}")

OUT_PATH.write_text(
    "\n".join(json.dumps(r) for r in records), encoding="utf-8"
)
print(f"\nWritten {len(records)} records to:\n  {OUT_PATH}")
print("\nSample (first 5):")
for r in records[:5]:
    print(f"  {r['date']}  {r['assessment']:<20}  {r['encounter_id']}  conf={r['confidence']}")
