"""Analyse the current remediation run - what are we learning?"""
import sqlite3, pathlib, json
from collections import Counter, defaultdict

DB = pathlib.Path("scripts/investigations/encounter_audit/remediation.db")
DISPUTES = pathlib.Path("scripts/investigations/encounter_audit/disputes.jsonl")

conn = sqlite3.connect(str(DB))

# -- 1. Overall rates for THIS session (after the fixes) -------------------
# The new run resumed at enc 2894. Filter to rows after that restart.
# We use the fact that applied counts dropped when we resumed,
# so analyse all rows but show session breakdown.

print("=" * 70)
print("CUMULATIVE DB STATE")
print("=" * 70)
total = conn.execute("SELECT COUNT(*) FROM remediated").fetchone()[0]
applied = conn.execute("SELECT COUNT(*) FROM remediated WHERE applied=1").fetchone()[0]
skipped = conn.execute("SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason='terminology_not_found'").fetchone()[0]
disputed = conn.execute("SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason!='terminology_not_found'").fetchone()[0]
enc = conn.execute("SELECT COUNT(*) FROM enc_processed").fetchone()[0]
print(f"Encounters processed : {enc}")
print(f"Total proposed       : {total}")
print(f"  Applied            : {applied}  ({100*applied/total:.1f}%)")
print(f"  Skipped (no term)  : {skipped}  ({100*skipped/total:.1f}%)")
print(f"  Disputed           : {disputed}  ({100*disputed/total:.1f}%)")

# -- 2. What is being applied? Top applied concepts ------------------------
print("\n" + "=" * 70)
print("TOP 20 APPLIED CHANGES (by concept_id)")
print("=" * 70)
rows = conn.execute("""
    SELECT action, concept_id, COUNT(*) as n
    FROM remediated WHERE applied=1
    GROUP BY action, concept_id
    ORDER BY n DESC LIMIT 20
""").fetchall()
for action, cid, n in rows:
    print(f"  {action:18s} {str(cid):25s} {n:4d}x")

# -- 3. Top skipped terms (terminology not found) --------------------------
print("\n" + "=" * 70)
print("TOP 30 SKIPPED SEARCH TERMS (terminology_not_found)")
print("=" * 70)
rows = conn.execute("""
    SELECT concept_id, COUNT(*) as n
    FROM remediated
    WHERE applied=0 AND sonnet_reason='terminology_not_found'
    GROUP BY concept_id
    ORDER BY n DESC LIMIT 30
""").fetchall()
for term, n in rows:
    print(f"  {n:4d}x  {term}")

# -- 4. Top dispute reasons from Sonnet ------------------------------------
print("\n" + "=" * 70)
print("TOP 25 DISPUTE REASONS (Sonnet said no)")
print("=" * 70)
rows = conn.execute("""
    SELECT sonnet_reason, COUNT(*) as n
    FROM remediated
    WHERE applied=0 AND sonnet_reason!='terminology_not_found'
    GROUP BY sonnet_reason
    ORDER BY n DESC LIMIT 25
""").fetchall()
for reason, n in rows:
    short = reason[:90] if reason else "(null)"
    print(f"  {n:4d}x  {short}")

# -- 5. How many add proposals are now resolving vs. first run? ------------
print("\n" + "=" * 70)
print("ADD ACTION BREAKDOWN")
print("=" * 70)
add_applied = conn.execute("SELECT COUNT(*) FROM remediated WHERE action='add' AND applied=1").fetchone()[0]
add_not = conn.execute("SELECT COUNT(*) FROM remediated WHERE action='add' AND applied=0").fetchone()[0]
add_no_term = conn.execute("SELECT COUNT(*) FROM remediated WHERE action='add' AND applied=0 AND sonnet_reason='terminology_not_found'").fetchone()[0]
add_disputed = conn.execute("SELECT COUNT(*) FROM remediated WHERE action='add' AND applied=0 AND sonnet_reason!='terminology_not_found'").fetchone()[0]
print(f"  ADD applied        : {add_applied}")
print(f"  ADD not applied    : {add_not}")
print(f"    - no term found  : {add_no_term}  ({100*add_no_term/max(1,add_not):.0f}% of not-applied adds)")
print(f"    - Sonnet disputed: {add_disputed}  ({100*add_disputed/max(1,add_not):.0f}% of not-applied adds)")

# -- 6. Recent batch rate (last 500 rows) ----------------------------------
print("\n" + "=" * 70)
print("RECENT BATCH (last 500 proposed changes)")
print("=" * 70)
rows = conn.execute("""
    SELECT applied, sonnet_reason
    FROM remediated ORDER BY rowid DESC LIMIT 500
""").fetchall()
recent_applied = sum(1 for r in rows if r[0] == 1)
recent_no_term = sum(1 for r in rows if r[0] == 0 and r[1] == 'terminology_not_found')
recent_disputed = sum(1 for r in rows if r[0] == 0 and r[1] != 'terminology_not_found')
print(f"  In last 500 rows:")
print(f"    Applied           : {recent_applied}")
print(f"    Skipped (no term) : {recent_no_term}")
print(f"    Disputed          : {recent_disputed}")
if recent_applied + recent_no_term + recent_disputed > 0:
    apply_rate = 100 * recent_applied / (recent_applied + recent_no_term + recent_disputed)
    skip_rate  = 100 * recent_no_term / (recent_applied + recent_no_term + recent_disputed)
    print(f"    Apply rate        : {apply_rate:.1f}%  (up from ~4% in old run?)")
    print(f"    Skip rate         : {skip_rate:.1f}%  (was ~50% before tag stripping)")

conn.close()
