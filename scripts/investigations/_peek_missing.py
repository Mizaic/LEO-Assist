"""Peek at the structure of missing/overcoded findings in the dry-run DB."""

import sqlite3, json
from pathlib import Path
from collections import Counter

con = sqlite3.connect(
    "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
)

rows = con.execute("SELECT result_json FROM encounters WHERE status='done'").fetchall()

missing_counter: Counter = Counter()
overcoded_counter: Counter = Counter()
sample_missing: list = []

for (rj,) in rows:
    if not rj:
        continue
    d = json.loads(rj)
    for m in d.get("missing") or []:
        key = f"[{m.get('concept_id','?')}] {m.get('term') or m.get('snomed_name') or m.get('name','?')}"
        missing_counter[key] += 1
        if len(sample_missing) < 3:
            sample_missing.append(m)
    for o in d.get("overcoded") or []:
        key = f"[{o.get('concept_id','?')}] {o.get('term') or o.get('snomed_name') or o.get('name','?')}"
        overcoded_counter[key] += 1

print("=== TOP MISSING (by frequency) ===")
for label, n in missing_counter.most_common(15):
    print(f"  x{n}  {label}")

print("\n=== TOP OVERCODED (by frequency) ===")
for label, n in overcoded_counter.most_common(10):
    print(f"  x{n}  {label}")

print("\n=== SAMPLE missing entry keys ===")
for s in sample_missing:
    print(" ", list(s.keys()), "->", s)

con.close()
