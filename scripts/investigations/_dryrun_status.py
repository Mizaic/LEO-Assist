"""Quick status check for the dry-run audit DB."""
import sqlite3, json
from pathlib import Path

db = Path("scripts/investigations/encounter_audit_dryrun/encounter_audit.db")
con = sqlite3.connect(str(db))

print("=== STATUS ===")
for row in con.execute("SELECT status, count(1) FROM encounters GROUP BY status"):
    print(f"  {row[0]}: {row[1]}")

print("\n=== VERDICTS (done only) ===")
for row in con.execute(
    "SELECT json_extract(result_json, '$.encounter_assessment') AS v, count(1) AS n"
    " FROM encounters WHERE status='done' GROUP BY v ORDER BY n DESC"
):
    print(f"  {row[0]}: {row[1]}")

print("\n=== FINDINGS TOTALS ===")
row = con.execute(
    "SELECT"
    "  coalesce(sum(json_array_length(json_extract(result_json, '$.missing'))), 0),"
    "  coalesce(sum(json_array_length(json_extract(result_json, '$.overcoded'))), 0),"
    "  coalesce(sum(json_array_length(json_extract(result_json, '$.wrong_assertion'))), 0)"
    " FROM encounters WHERE status='done'"
).fetchone()
print(f"  missing codes : {row[0]}")
print(f"  overcoded     : {row[1]}")
print(f"  wrong assert. : {row[2]}")

print("\n=== TOP MISSING CONCEPTS ===")
for r in con.execute(
    "SELECT json_extract(value, '$.snomed_name') AS name,"
    "       json_extract(value, '$.concept_id') AS cid,"
    "       count(1) AS n"
    " FROM encounters, json_each(json_extract(result_json, '$.missing'))"
    " WHERE status='done'"
    " GROUP BY cid ORDER BY n DESC LIMIT 10"
):
    print(f"  [{r[2]}] {r[0]}  x{r[1]}")

con.close()
