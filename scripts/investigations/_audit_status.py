"""Quick status report from the running audit SQLite DB."""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "encounter_audit" / "encounter_audit.db"
db = sqlite3.connect(db_path)

status_rows = db.execute(
    "SELECT status, COUNT(*) FROM encounters GROUP BY status ORDER BY COUNT(*) DESC"
).fetchall()
total = db.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
done = next((c for s, c in status_rows if s == "done"), 0)
errors = next((c for s, c in status_rows if s == "error"), 0)
pending = next((c for s, c in status_rows if s == "pending"), 0)

print("=== Progress ===")
print(f"  Done:    {done:,}  /  {total:,}  ({100 * done // max(total, 1)}%)")
print(f"  Pending: {pending:,}")
print(f"  Errors:  {errors:,}")

assess_rows = db.execute("""
    SELECT json_extract(result_json, '$.encounter_assessment') AS assess,
           COUNT(*) AS n
    FROM encounters
    WHERE status = 'done' AND result_json IS NOT NULL
    GROUP BY assess
    ORDER BY n DESC
""").fetchall()
print("\n=== Assessment breakdown ===")
for a, n in assess_rows:
    pct = 100 * n // max(done, 1)
    print(f"  {(a or 'null'):<20s} {n:5,}  ({pct}%)")

missing_enc = db.execute("""
    SELECT COUNT(*) FROM encounters
    WHERE status = 'done'
      AND json_array_length(json_extract(result_json, '$.missing')) > 0
""").fetchone()[0]
overcoded_enc = db.execute("""
    SELECT COUNT(*) FROM encounters
    WHERE status = 'done'
      AND json_array_length(json_extract(result_json, '$.overcoded')) > 0
""").fetchone()[0]
wrong_enc = db.execute("""
    SELECT COUNT(*) FROM encounters
    WHERE status = 'done'
      AND json_array_length(json_extract(result_json, '$.wrong_assertion')) > 0
""").fetchone()[0]

print("\n=== Encounters with issues ===")
print(f"  Missing codes:    {missing_enc:,}  ({100 * missing_enc // max(done, 1)}%)")
print(f"  Overcoded:        {overcoded_enc:,}  ({100 * overcoded_enc // max(done, 1)}%)")
print(f"  Wrong assertion:  {wrong_enc:,}  ({100 * wrong_enc // max(done, 1)}%)")

sf_total = db.execute("SELECT COUNT(*) FROM surface_form_gaps").fetchone()[0]
print(f"\n=== Surface form gaps: {sf_total:,} ===")

top_missing = db.execute("""
    SELECT json_extract(value, '$.term') AS term,
           json_extract(value, '$.severity') AS severity,
           COUNT(*) AS n
    FROM encounters, json_each(json_extract(result_json, '$.missing'))
    WHERE status = 'done' AND result_json IS NOT NULL
    GROUP BY term
    ORDER BY n DESC
    LIMIT 15
""").fetchall()
print("\n=== Top 15 most common missing terms ===")
for term, sev, n in top_missing:
    print(f"  {n:4d}x  [{(sev or '?'):<8s}]  {term}")

top_overcoded = db.execute("""
    SELECT json_extract(value, '$.name') AS name, COUNT(*) AS n
    FROM encounters, json_each(json_extract(result_json, '$.overcoded'))
    WHERE status = 'done' AND result_json IS NOT NULL
    GROUP BY name
    ORDER BY n DESC
    LIMIT 10
""").fetchall()
print("\n=== Top 10 most common overcoded terms ===")
for name, n in top_overcoded:
    print(f"  {n:4d}x  {name}")

db.close()
