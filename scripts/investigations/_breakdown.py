"""Full breakdown of remediation categories."""

import sqlite3
import json
from pathlib import Path
from collections import Counter

DB = Path("scripts/investigations/encounter_audit/encounter_audit.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT result_json FROM encounters WHERE status='done'")

oc_names = Counter()
miss_crit = Counter()
miss_high_sample = Counter()
wa_pairs = Counter()

for row in cur.fetchall():
    d = json.loads(row["result_json"])
    for item in d.get("overcoded", []):
        oc_names[item.get("name", "?")] += 1
    for item in d.get("missing", []):
        sev = item.get("severity", "")
        term = item.get("snomed_search") or item.get("term", "?")
        if sev == "critical":
            miss_crit[term] += 1
        elif sev == "high":
            miss_high_sample[term] += 1
    for item in d.get("wrong_assertion", []):
        cur_a = item.get("current_assertion")
        sug_a = item.get("suggested_assertion")
        if cur_a != sug_a:
            wa_pairs[(cur_a, sug_a)] += 1

conn.close()

print("Top 20 overcoded concepts (delete candidates):")
for name, cnt in oc_names.most_common(20):
    print(f"  {cnt:5d}  {name}")

print("\nTop 20 missing CRITICAL (add candidates):")
for name, cnt in miss_crit.most_common(20):
    print(f"  {cnt:5d}  {name}")

print("\nTop 15 missing HIGH:")
for name, cnt in miss_high_sample.most_common(15):
    print(f"  {cnt:5d}  {name}")

print("\nWrong assertion transitions (current -> suggested):")
for (cur_a, sug_a), cnt in wa_pairs.most_common():
    print(f"  {cnt:4d}  {cur_a} -> {sug_a}")
