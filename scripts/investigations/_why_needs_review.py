"""Analyse why encounters landed in needs_review.

Buckets them by root cause so we know which levers to pull.
"""
import sqlite3, json
from pathlib import Path
from collections import Counter

con = sqlite3.connect(
    "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
)

rows = con.execute(
    "SELECT encounter_id, result_json FROM encounters"
    " WHERE status='done'"
    "  AND json_extract(result_json,'$.encounter_assessment')='needs_review'"
).fetchall()

confidence: list[float] = []
notes_samples: list[str] = []
iter_counts: Counter = Counter()
low_conf_with_no_findings: int = 0
has_findings: int = 0
errors_present: int = 0
hit_iter_limit: int = 0

for eid, rj in rows:
    d = json.loads(rj)
    meta = d.get("metadata") or {}
    conf = float(d.get("confidence") or 0)
    iters = int(meta.get("tool_iterations") or 0)
    errs = d.get("_errors") or []
    miss = d.get("missing") or []
    over = d.get("overcoded") or []
    wrong = d.get("wrong_assertion") or []
    notes = str(d.get("notes") or "")

    confidence.append(conf)
    iter_counts[iters] += 1

    if errs:
        errors_present += 1
    if miss or over or wrong:
        has_findings += 1
    else:
        low_conf_with_no_findings += 1
    if iters >= 10:
        hit_iter_limit += 1

    if len(notes_samples) < 20 and notes:
        notes_samples.append(f"[conf={conf:.2f} iters={iters}] {notes[:140]}")

n = len(rows)
avg_conf = sum(confidence) / n if n else 0
print(f"Total needs_review: {n}")
print(f"  has findings (miss/over/wrong): {has_findings}  ({has_findings/n*100:.0f}%)")
print(f"  no findings but needs_review:   {low_conf_with_no_findings}  ({low_conf_with_no_findings/n*100:.0f}%)")
print(f"  had _errors:                    {errors_present}")
print(f"  hit iteration limit (>=10):     {hit_iter_limit}")
print(f"  avg confidence:                 {avg_conf:.2f}")

print(f"\nConfidence distribution:")
buckets = {
    "0.0":     sum(1 for c in confidence if c == 0),
    "0.01-0.49": sum(1 for c in confidence if 0 < c < 0.5),
    "0.50-0.69": sum(1 for c in confidence if 0.5 <= c < 0.7),
    "0.70-0.84": sum(1 for c in confidence if 0.7 <= c < 0.85),
    ">=0.85":  sum(1 for c in confidence if c >= 0.85),
}
for label, cnt in buckets.items():
    print(f"  {label}: {cnt}")

print(f"\nTool iteration distribution:")
for iters, cnt in sorted(iter_counts.items()):
    print(f"  {iters} iters: {cnt}")

print(f"\nSample agent notes:")
for s in notes_samples:
    print(f"  {s}")

con.close()
