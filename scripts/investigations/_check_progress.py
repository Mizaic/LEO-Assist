"""Quick progress report for the running encounter audit."""
import json
import sqlite3
import time

DB = (
    r"c:\Users\RobertSmith\Documents\GitHub\LEO-AI-CORE"
    r"\scripts\investigations\encounter_audit\encounter_audit.db"
)

_NORM = {
    "not clean": "has_issues",
    "not_clean": "has_issues",
    "has issues": "has_issues",
    "has_issue": "has_issues",
    "issues_found": "has_issues",
    "errors_found": "has_issues",
    "dirty": "has_issues",
    "incomplete": "needs_review",
    "requires_review": "needs_review",
    "needs_attention": "needs_review",
}


def _normalise(assessment: str) -> str:
    return _NORM.get(assessment.lower().strip(), assessment)


db = sqlite3.connect(DB)
status_rows = db.execute(
    "SELECT status, COUNT(*) FROM encounters GROUP BY status"
).fetchall()
status_dict = dict(status_rows)
print("Status counts:", status_dict)

done = status_dict.get("done", 0)
pending = status_dict.get("pending", 0)
total = sum(status_dict.values())

done_rows = db.execute(
    "SELECT result_json, processed_at FROM encounters WHERE status='done'"
).fetchall()

assessments: dict[str, int] = {}
missing_total = 0
overcoded_total = 0
wrong_assertion_total = 0
critical_count = 0
high_count = 0
term_counts: dict[str, int] = {}
top_critical: list[tuple[str, str, str]] = []  # (patient, date, term)

for (r, proc_at) in done_rows:
    if not r:
        continue
    d = json.loads(r)
    a = _normalise(d.get("encounter_assessment", "?"))
    assessments[a] = assessments.get(a, 0) + 1
    missing = d.get("missing", [])
    overcoded = d.get("overcoded", [])
    wrong = d.get("wrong_assertion", [])
    missing_total += len(missing)
    overcoded_total += len(overcoded)
    wrong_assertion_total += len(wrong)
    for m in missing:
        sev = m.get("severity", "")
        if sev == "critical":
            critical_count += 1
            meta = d.get("_meta", {})
            top_critical.append((
                meta.get("patient_id", "?"),
                meta.get("date", "?"),
                m.get("term", "?"),
            ))
        elif sev == "high":
            high_count += 1
        t = m.get("term", "").strip().lower()
        if t:
            term_counts[t] = term_counts.get(t, 0) + 1

print(f"\nAssessments (normalised, n={done}):")
for k, v in sorted(assessments.items(), key=lambda x: -x[1]):
    pct = 100 * v / done if done else 0
    print(f"  {v:5d} ({pct:4.1f}%)  {k}")

print(f"\nMissing flags: {missing_total}")
print(f"  critical: {critical_count}")
print(f"  high:     {high_count}")
print(f"Overcoded flags: {overcoded_total}")
print(f"Wrong assertion: {wrong_assertion_total}")

top10 = sorted(term_counts.items(), key=lambda x: -x[1])[:15]
print("\nTop 15 most frequently missing terms:")
for term, cnt in top10:
    print(f"  {cnt:4d}  {term}")

if top_critical:
    print(f"\nCritical missing (first 10 of {len(top_critical)}):")
    for pat, dt, term in top_critical[:10]:
        print(f"  patient={pat}  date={dt}  term={term}")

# Estimate completion
# Use the earliest processed_at and latest to estimate rate
times = [
    r for (_, r) in done_rows if r
]
if len(times) >= 2:
    times_sorted = sorted(times)
    t_start = time.strptime(times_sorted[0][:19], "%Y-%m-%dT%H:%M:%S")
    t_end = time.strptime(times_sorted[-1][:19], "%Y-%m-%dT%H:%M:%S")
    elapsed_s = time.mktime(t_end) - time.mktime(t_start)
    if elapsed_s > 0:
        rate_per_min = done / (elapsed_s / 60)
        remaining_min = pending / rate_per_min if rate_per_min else 0
        print(
            f"\nRate: {rate_per_min:.1f}/min  |  "
            f"Remaining: {pending}  |  "
            f"ETA: ~{remaining_min / 60:.1f} hours"
        )

db.close()
