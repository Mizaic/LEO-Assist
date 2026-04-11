"""Analyse Phase 3 surface form gaps in detail."""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "encounter_audit" / "encounter_audit.db"
db = sqlite3.connect(db_path)

total = db.execute("SELECT COUNT(*) FROM surface_form_gaps").fetchone()[0]
print(f"Total surface form gaps: {total:,}")

by_type = db.execute(
    "SELECT gap_type, COUNT(*) FROM surface_form_gaps GROUP BY gap_type ORDER BY COUNT(*) DESC"
).fetchall()
print("\nBy gap type:")
for t, n in by_type:
    print(f"  {t:<15s} {n:,}")

print("\nTop 25 gaps by target concept (what we are trying to resolve TO):")
by_concept = db.execute("""
    SELECT expected_name, gap_type, COUNT(*) AS n
    FROM surface_form_gaps
    GROUP BY expected_name, gap_type
    ORDER BY n DESC
    LIMIT 25
""").fetchall()
for name, gtype, n in by_concept:
    print(f"  {n:4d}x  [{gtype:<12s}]  {name}")

print("\nSample not_found evidence phrases (totally absent from resolver):")
rows = db.execute("""
    SELECT evidence, expected_name, expected_concept_id
    FROM surface_form_gaps
    WHERE gap_type = 'not_found'
    ORDER BY ROWID
    LIMIT 20
""").fetchall()
for ev, name, cid in rows:
    ev_short = (ev or "")[:90]
    print(f"  [{ev_short}]")
    print(f"       -> {name}  ({cid})")

print("\nSample wrong_rank (resolver returns something else in top 4):")
rows = db.execute("""
    SELECT evidence, expected_name, resolver_top_result, resolver_top_score
    FROM surface_form_gaps
    WHERE gap_type = 'wrong_rank'
      AND evidence NOT LIKE '%Surgery:%'
      AND evidence NOT LIKE '%:%:%'
    ORDER BY ROWID
    LIMIT 20
""").fetchall()
for ev, exp, top, score in rows:
    ev_short = (ev or "")[:70]
    print(f"  [{ev_short}]")
    print(f"       Expected: {exp}")
    print(f"       Got:      {top}  (score {score:.2f})")

db.close()
