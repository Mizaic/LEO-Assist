"""Check for overlapping audit runs by inspecting timestamps in each trail file."""
import json, glob, os
from datetime import datetime

trail_files = sorted(glob.glob("scripts/agentic_audit_trail_*.jsonl"))

runs = []
for path in trail_files:
    timestamps = []
    label_ids = set()
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                ts = rec.get("timestamp")
                if ts:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                lid = rec.get("label_id")
                if lid:
                    label_ids.add(lid)
            except Exception:
                pass
    if timestamps:
        runs.append({
            "file": os.path.basename(path),
            "first": min(timestamps),
            "last": max(timestamps),
            "count": len(timestamps),
            "label_ids": label_ids,
        })

runs.sort(key=lambda r: r["first"])

print(f"{'File':<45} {'First entry':<25} {'Last entry':<25} {'Records':>8}")
print("-" * 110)
for r in runs:
    print(f"{r['file']:<45} {str(r['first']):<25} {str(r['last']):<25} {r['count']:>8}")

print()
print("=== Overlap check ===")
for i, a in enumerate(runs):
    for b in runs[i+1:]:
        # overlap if one starts before the other ends
        if a["first"] <= b["last"] and b["first"] <= a["last"]:
            overlap_start = max(a["first"], b["first"])
            overlap_end = min(a["last"], b["last"])
            # Check for shared label_ids (actual duplicate work)
            shared = a["label_ids"] & b["label_ids"]
            print(f"OVERLAP: {a['file']} <-> {b['file']}")
            print(f"  Time overlap: {overlap_start} -> {overlap_end}")
            print(f"  Shared label_ids (duplicate records audited): {len(shared)}")
