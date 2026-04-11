"""Deep-dive on the current remediation run - what are we actually learning?"""

import sqlite3, pathlib, json
from collections import Counter

DB = pathlib.Path("scripts/investigations/encounter_audit/remediation.db")
conn = sqlite3.connect(str(DB))

# -----------------------------------------------------------------------
# 1. What 20 adds DID Sonnet agree with?
# -----------------------------------------------------------------------
print("=" * 70)
print("1. SUCCESSFUL ADDS (Sonnet agreed)")
print("=" * 70)
rows = conn.execute("""
    SELECT concept_id, new_value, sonnet_conf, COUNT(*) as n
    FROM remediated
    WHERE action='add' AND applied=1
    GROUP BY concept_id, new_value
    ORDER BY n DESC
""").fetchall()
for cid, nv, conf, n in rows:
    print(f"  {n:3d}x  conf={conf or '?':5}  {cid}  {(nv or '')[:60]}")

# -----------------------------------------------------------------------
# 2. The 126 null reasons - worker errors?
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("2. NULL REASON DISPUTES - sample of error messages")
print("=" * 70)
rows = conn.execute("""
    SELECT encounter_id, action, concept_id, error_msg, sonnet_conf, processed_at
    FROM remediated
    WHERE applied=0 AND sonnet_reason IS NULL
    LIMIT 15
""").fetchall()
for enc, action, cid, err, conf, ts in rows:
    print(f"  {action:18s} {cid[:30]:30s} conf={conf}  err={err}  ts={ts}")

# -----------------------------------------------------------------------
# 3. Recent batch (last 300 rows from the fixed run) - skip breakdown
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("3. RECENT 300 ROWS - what's still skipping?")
print("=" * 70)
rows = conn.execute("""
    SELECT concept_id, sonnet_reason, applied
    FROM remediated ORDER BY rowid DESC LIMIT 300
""").fetchall()
recent_skips = [r for r in rows if not r[2] and r[1] == "terminology_not_found"]
skip_terms = Counter(r[0] for r in recent_skips)
print(f"  Skipped (no term) in last 300: {len(recent_skips)}")
for term, n in skip_terms.most_common(15):
    print(f"    {n:3d}x  {term}")

# -----------------------------------------------------------------------
# 4. What is Sonnet disputing for ADD actions?
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("4. TOP ADD DISPUTE REASONS (Sonnet said no to new code)")
print("=" * 70)
rows = conn.execute("""
    SELECT sonnet_reason, COUNT(*) as n
    FROM remediated
    WHERE action='add' AND applied=0 AND sonnet_reason != 'terminology_not_found'
          AND sonnet_reason IS NOT NULL
    GROUP BY sonnet_reason
    ORDER BY n DESC LIMIT 20
""").fetchall()
for reason, n in rows:
    print(f"  {n:4d}x  {(reason or '')[:100]}")

# -----------------------------------------------------------------------
# 5. What is Sonnet disputing for DELETE actions?
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("5. TOP DELETE DISPUTE REASONS (non-null, non-empty-coding)")
print("=" * 70)
rows = conn.execute("""
    SELECT sonnet_reason, COUNT(*) as n
    FROM remediated
    WHERE action='delete' AND applied=0 AND sonnet_reason IS NOT NULL
          AND sonnet_reason NOT LIKE '%0 concepts%'
          AND sonnet_reason NOT LIKE '%zero concepts%'
          AND sonnet_reason NOT LIKE '%nothing to delete%'
    GROUP BY sonnet_reason
    ORDER BY n DESC LIMIT 20
""").fetchall()
for reason, n in rows:
    print(f"  {n:4d}x  {(reason or '')[:100]}")

# -----------------------------------------------------------------------
# 6. Progress summary
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("6. PROGRESS RATES (by session)")
print("=" * 70)
# Batch markers from progress log lines in remediation runs
enc = conn.execute("SELECT COUNT(*) FROM enc_processed").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM remediated").fetchone()[0]
applied = conn.execute("SELECT COUNT(*) FROM remediated WHERE applied=1").fetchone()[0]
add_applied = conn.execute(
    "SELECT COUNT(*) FROM remediated WHERE action='add' AND applied=1"
).fetchone()[0]
del_applied = conn.execute(
    "SELECT COUNT(*) FROM remediated WHERE action='delete' AND applied=1"
).fetchone()[0]
upd_applied = conn.execute(
    "SELECT COUNT(*) FROM remediated WHERE action='update_assertion' AND applied=1"
).fetchone()[0]

print(f"  Encounters processed : {enc}/10136 ({100*enc/10136:.1f}%)")
print(f"  Total proposed       : {total}")
print(
    f"  Applied total        : {applied}  (ADD={add_applied}  DEL={del_applied}  UPD={upd_applied})"
)
print(f"  Remaining encounters : ~{10136-enc}")

conn.close()
