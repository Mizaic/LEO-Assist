"""Quantify duplication across all audit trail files."""
import json, glob, collections
from datetime import datetime

trail_files = sorted(glob.glob("scripts/agentic_audit_trail_*.jsonl"))

all_label_ids = []
label_audit_count = collections.Counter()  # how many times each label was audited
label_last_run = {}   # last trail file that audited each label

for path in trail_files:
    fname = path.split("\\")[-1].split("/")[-1]
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                lid = rec.get("label_id")
                if lid:
                    label_audit_count[lid] += 1
                    label_last_run[lid] = fname
            except Exception:
                pass

total_unique   = len(label_audit_count)
total_audits   = sum(label_audit_count.values())
duplicated     = sum(1 for c in label_audit_count.values() if c > 1)
max_dups       = max(label_audit_count.values())

dup_dist = collections.Counter(label_audit_count.values())

print(f"Unique label_ids audited:  {total_unique:,}")
print(f"Total audit events:        {total_audits:,}")
print(f"Duplication factor:        {total_audits/total_unique:.1f}x")
print(f"Records audited >1 time:   {duplicated:,} ({100*duplicated/total_unique:.1f}%)")
print(f"Max times one record seen: {max_dups}")
print()
print("Audit count distribution:")
for count in sorted(dup_dist.keys()):
    print(f"  Audited {count}x: {dup_dist[count]:,} records")

# Which trail file was each record's LAST audit?
last_run_dist = collections.Counter(label_last_run.values())
print()
print("Records whose LAST audit was in each file (i.e. winning version):")
for fname, cnt in sorted(last_run_dist.items(), key=lambda x: x[0]):
    print(f"  {fname}: {cnt:,}")
