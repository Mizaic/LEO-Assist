"""Full post-remediation summary: what was applied, top concepts, disputes."""
import sqlite3
from pathlib import Path
from collections import defaultdict

DB = Path("scripts/investigations/encounter_audit/remediation.db")
db = sqlite3.connect(DB)
cur = db.cursor()

print("=" * 70)
print("REMEDIATION FINAL SUMMARY (both passes combined)")
print("=" * 70)

# Overall counts
total_enc = cur.execute("SELECT COUNT(*) FROM enc_processed").fetchone()[0]
total_prop = cur.execute("SELECT COUNT(*) FROM remediated").fetchone()[0]
applied = cur.execute("SELECT COUNT(*) FROM remediated WHERE applied=1").fetchone()[0]
by_action = cur.execute("""
    SELECT action, COUNT(*) FROM remediated WHERE applied=1 GROUP BY action
""").fetchall()

print(f"\nEncounters processed : {total_enc:,}")
print(f"Total proposed       : {total_prop:,}")
print(f"Total applied        : {applied:,}")
for action, n in sorted(by_action, key=lambda x: -x[1]):
    print(f"  {action:25s}: {n:,}")

skipped = cur.execute(
    "SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason='terminology_not_found'"
).fetchone()[0]
disputed = cur.execute(
    "SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason!='terminology_not_found' AND sonnet_reason IS NOT NULL"
).fetchone()[0]
print(f"Terminology skips    : {skipped:,}")
print(f"Sonnet disputes      : {disputed:,}")

# Top ADD concepts applied
print("\n" + "=" * 70)
print("TOP 30 CONCEPTS ADDED TO NEO4J")
print("=" * 70)
rows = cur.execute("""
    SELECT concept_id, COUNT(*) AS n FROM remediated
    WHERE applied=1 AND action='add'
    GROUP BY concept_id ORDER BY n DESC LIMIT 30
""").fetchall()
for term, n in rows:
    print(f"  {n:4d}x  {term}")

# Top DEL concepts removed
print("\n" + "=" * 70)
print("TOP 20 CONCEPTS DELETED FROM NEO4J")
print("=" * 70)
rows = cur.execute("""
    SELECT concept_id, COUNT(*) AS n FROM remediated
    WHERE applied=1 AND action='delete'
    GROUP BY concept_id ORDER BY n DESC LIMIT 20
""").fetchall()
for term, n in rows:
    print(f"  {n:4d}x  {term}")

# Top assertion updates
print("\n" + "=" * 70)
print("TOP 20 ASSERTION UPDATES")
print("=" * 70)
rows = cur.execute("""
    SELECT old_value, new_value, COUNT(*) AS n FROM remediated
    WHERE applied=1 AND action='update_assertion'
    GROUP BY old_value, new_value ORDER BY n DESC LIMIT 20
""").fetchall()
for old, new, n in rows:
    print(f"  {n:4d}x  {old} -> {new}")

# Remaining skips after pass 2
print("\n" + "=" * 70)
print("REMAINING TERMINOLOGY GAPS (still not resolvable)")
print("=" * 70)
rows = cur.execute("""
    SELECT concept_id, COUNT(*) AS n FROM remediated
    WHERE applied=0 AND sonnet_reason='terminology_not_found'
    GROUP BY concept_id ORDER BY n DESC LIMIT 30
""").fetchall()
for term, n in rows:
    print(f"  {n:4d}x  {term}")

# Top Sonnet dispute reasons
print("\n" + "=" * 70)
print("TOP 10 SONNET DISPUTE REASONS")
print("=" * 70)
rows = cur.execute("""
    SELECT sonnet_reason, COUNT(*) AS n FROM remediated
    WHERE applied=0 AND sonnet_reason NOT IN ('terminology_not_found','')
    AND sonnet_reason IS NOT NULL
    GROUP BY sonnet_reason ORDER BY n DESC LIMIT 10
""").fetchall()
for reason, n in rows:
    print(f"  {n:4d}x  {reason[:100]}")

db.close()
