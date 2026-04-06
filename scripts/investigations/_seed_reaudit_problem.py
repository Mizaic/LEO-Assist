"""Seed a fresh audit DB with the 3855 problem encounters for re-audit.

Reads problem_encounters.jsonl (produced by _list_problem_encounters.py) and
inserts every encounter as 'pending' into a new CheckpointDB so the audit
script can re-process them with the current prompt.

Usage
-----
    python scripts/investigations/_seed_reaudit_problem.py

Output
------
    scripts/investigations/encounter_audit_reaudit/encounter_audit.db
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.investigations._audit_db import CheckpointDB  # noqa: E402

SRC = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "problem_encounters.jsonl"
)
OUT_DIR = ROOT / "scripts" / "investigations" / "encounter_audit_reaudit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = OUT_DIR / "encounter_audit.db"

if not SRC.exists():
    print(f"ERROR: {SRC} not found. Run _list_problem_encounters.py first.")
    sys.exit(1)

records = [json.loads(line) for line in SRC.read_text(encoding="utf-8").splitlines() if line.strip()]
print(f"Loaded {len(records)} problem encounters from {SRC.name}")

db = CheckpointDB(DB_PATH)
inserted = db.insert_encounters(records)
counts = db.counts()
db.close()

print(f"DB: {DB_PATH}")
print(f"  Inserted (new):  {inserted}")
print(f"  Total pending:   {counts['total']}")
print()
print("Next step -- re-audit:")
print(
    "  python scripts/investigations/audit_encounter_coding.py"
    " --yes"
    " --skip-discovery"
    " --since 2024-01-01"
    " --until 2025-12-31"
    " --workers 5"
    " --cost-cap 500"
    " --output scripts/investigations/encounter_audit_reaudit"
    " --triggered-by manual"
)
