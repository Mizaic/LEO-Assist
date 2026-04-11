"""Count exactly which encounters need remediation and what type of fix."""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict

DB = Path("scripts/investigations/encounter_audit/encounter_audit.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM encounters WHERE status='done'")
total_done = cur.fetchone()[0]

cur.execute("SELECT encounter_id, result_json FROM encounters WHERE status='done'")

needs_overcoded_fix = []  # delete DOCUMENTS
needs_missing_critical = []  # add DOCUMENTS - critical
needs_missing_high = []  # add DOCUMENTS - high
needs_wrong_assertion = []  # update assertion
clean = 0
parse_errors = 0

for row in cur.fetchall():
    try:
        d = json.loads(row["result_json"])
    except Exception:
        parse_errors += 1
        continue

    overcoded = d.get("overcoded", [])
    missing = d.get("missing", [])
    wrong = [
        w
        for w in d.get("wrong_assertion", [])
        if w.get("current_assertion") != w.get("suggested_assertion")
    ]

    missing_crit = [m for m in missing if m.get("severity") == "critical"]
    missing_high = [m for m in missing if m.get("severity") == "high"]

    enc_id = row["encounter_id"]

    if overcoded:
        needs_overcoded_fix.append((enc_id, overcoded))
    if missing_crit:
        needs_missing_critical.append((enc_id, missing_crit))
    if missing_high:
        needs_missing_high.append((enc_id, missing_high))
    if wrong:
        needs_wrong_assertion.append((enc_id, wrong))

    if not overcoded and not missing_crit and not missing_high and not wrong:
        clean += 1

conn.close()

# -- Dedup encounter IDs that appear in multiple buckets
all_needing_work = set()
for enc_id, _ in needs_overcoded_fix:
    all_needing_work.add(enc_id)
for enc_id, _ in needs_missing_critical:
    all_needing_work.add(enc_id)
for enc_id, _ in needs_missing_high:
    all_needing_work.add(enc_id)
for enc_id, _ in needs_wrong_assertion:
    all_needing_work.add(enc_id)

# -- Item counts (individual findings, not encounters)
oc_items = sum(len(x) for _, x in needs_overcoded_fix)
crit_items = sum(len(x) for _, x in needs_missing_critical)
high_items = sum(len(x) for _, x in needs_missing_high)
wa_items = sum(len(x) for _, x in needs_wrong_assertion)

print(f"Total encounters audited:            {total_done:,}")
print(f"Parse errors:                        {parse_errors:,}")
print(f"Clean (no action needed):            {clean:,}")
print()
print(f"ENCOUNTERS needing work:             {len(all_needing_work):,}")
print()
print(
    f"  Overcoded (delete a code):         {len(needs_overcoded_fix):,} encounters  /  {oc_items:,} items"
)
print(
    f"  Missing CRITICAL (add a code):     {len(needs_missing_critical):,} encounters  /  {crit_items:,} items"
)
print(
    f"  Missing HIGH (add a code):         {len(needs_missing_high):,} encounters  /  {high_items:,} items"
)
print(
    f"  Wrong assertion (update):          {len(needs_wrong_assertion):,} encounters  /  {wa_items:,} items"
)
print()

# -- Sanity check: show top overcoded concepts
from collections import Counter

oc_concept_counter = Counter()
for _, items in needs_overcoded_fix:
    for item in items:
        name = item.get("name") or item.get("conceptId", "unknown")
        oc_concept_counter[name] += 1

print("Top 15 overcoded concepts:")
for name, cnt in oc_concept_counter.most_common(15):
    print(f"  {cnt:5d}  {name}")

print()
miss_counter = Counter()
for _, items in needs_missing_critical:
    for item in items:
        miss_counter[item.get("snomed_search") or item.get("term", "?")] += 1

print("Top 15 critical missing concepts:")
for name, cnt in miss_counter.most_common(15):
    print(f"  {cnt:5d}  {name}")

# -- Save encounter IDs to JSON for the remediation script
output = {
    "overcoded": {enc: items for enc, items in needs_overcoded_fix},
    "missing_critical": {enc: items for enc, items in needs_missing_critical},
    "missing_high": {enc: items for enc, items in needs_missing_high},
    "wrong_assertion": {enc: items for enc, items in needs_wrong_assertion},
}
out_path = Path("scripts/investigations/encounter_audit/remediation_plan.json")
out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
print(f"\nRemediation plan saved: {out_path}")
print(f"Total unique encounters to send to Sonnet: {len(all_needing_work):,}")
