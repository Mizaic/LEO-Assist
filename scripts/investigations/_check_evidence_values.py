"""Check if old evidence in Neo4j has embedded numeric values that should have been stripped."""

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Regex that matches a numeric value + unit (lab result pattern)
_VALUE_UNIT = re.compile(
    r"\d+(?:\.\d+)?[\s]?"
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|ml|l|fl|%|mmhg|kpa|bpm|miu|u/l|g/l|10\^)",
    re.IGNORECASE,
)

db = sqlite3.connect(
    str(ROOT / "scripts" / "investigations" / "encounter_audit" / "encounter_audit.db")
)
rows = db.execute(
    "SELECT evidence, expected_name, COUNT(*) n FROM surface_form_gaps"
    " WHERE length(evidence) < 100"
    " GROUP BY evidence ORDER BY n DESC"
).fetchall()
db.close()

has_value = [(ev, name, n) for ev, name, n in rows if _VALUE_UNIT.search(ev or "")]
no_value = [(ev, name, n) for ev, name, n in rows if not _VALUE_UNIT.search(ev or "")]

print(f"Total unique gap phrases: {len(rows)}")
print(f"  With embedded lab values (old data, not stripped): {len(has_value)}")
print(f"  Clean phrases (no embedded value):                 {len(no_value)}")

print(f"\nTop 20 with embedded values:")
for ev, name, n in has_value[:20]:
    print(f"  {n}x  '{ev}'  ->  {name[:50]}")

print(f"\nSample of clean phrases:")
for ev, name, n in no_value[:15]:
    print(f"  {n}x  '{ev}'  ->  {name[:50]}")
