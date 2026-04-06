"""Quick progress check for the problem-encounters re-audit."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "scripts" / "investigations" / "encounter_audit_reaudit" / "encounter_audit.db"

con = sqlite3.connect(str(DB))
total = con.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
status_rows = con.execute(
    "SELECT status, COUNT(*) FROM encounters GROUP BY status ORDER BY 2 DESC"
).fetchall()
assess_rows = con.execute(
    "SELECT json_extract(result_json, '$.encounter_assessment') as a, COUNT(*) n"
    " FROM encounters WHERE status='done' GROUP BY a ORDER BY n DESC"
).fetchall()
cost = con.execute(
    "SELECT SUM(cost_usd) FROM encounters WHERE status='done'"
).fetchone()[0] or 0.0
gaps = con.execute("SELECT COUNT(*) FROM surface_form_gaps").fetchone()[0]
ner = con.execute("SELECT COUNT(*) FROM ner_examples").fetchone()[0]
con.close()

done = next((n for s, n in status_rows if s == "done"), 0)
errors = next((n for s, n in status_rows if s == "error"), 0)
pending = next((n for s, n in status_rows if s == "pending"), 0)
pct = round(100 * done / total, 1) if total else 0

print(f"\n=== Re-audit progress: {done}/{total} ({pct}%) ===")
print(f"  pending={pending}  errors={errors}  cost=${cost:.2f}")
print(f"  surface_gaps={gaps}  ner_examples={ner}")
print("\n  Assessments so far:")
for a, n in assess_rows:
    print(f"    {(a or 'null'):<25} {n:>5}")

if pending > 0 and done > 0:
    rate = done / (done + pending)
    est_remaining_min = round((pending / done) * (done * 3) / 60 / 5, 0)
    print(f"\n  Estimated remaining: ~{int(est_remaining_min)} min at 5 workers")
