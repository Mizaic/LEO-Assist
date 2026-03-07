"""
Comprehensive quality review of audit trail output.
For each label_id, takes only the LAST audit (most recent trail file by timestamp).
Then analyses whether the new logic is generating good gold data.
"""
import json, glob, collections, statistics
from datetime import datetime

trail_files = sorted(glob.glob("scripts/agentic_audit_trail_*.jsonl"))

# Build: label_id -> most recent record
latest: dict[str, dict] = {}
for path in trail_files:
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                lid = rec.get("label_id")
                ts  = rec.get("timestamp", "")
                if lid and (lid not in latest or ts > latest[lid]["timestamp"]):
                    latest[lid] = rec
            except Exception:
                pass

records = list(latest.values())
print(f"Unique records (latest version each): {len(records):,}")
print()

# ── 1. Top-level verdicts ─────────────────────────────────────────────────────
verdicts = collections.Counter(r.get("record_verdict","") for r in records)
print("=== Record verdicts ===")
for v, c in verdicts.most_common():
    print(f"  {v}: {c:,} ({100*c/len(records):.1f}%)")

# ── 2. Auto-fixes breakdown ───────────────────────────────────────────────────
fix_verdicts   = collections.Counter()
fix_fields     = collections.Counter()
add_entities   = []
remove_entities = []

for r in records:
    for fx in r.get("auto_fixes", []):
        v = fx.get("verdict","")
        f = str(fx.get("field",""))
        fix_verdicts[v] += 1
        fix_fields[(v, f)] += 1
        if v == "add":
            add_entities.append(fx)
        elif v == "remove":
            remove_entities.append(fx)

total_fixes = sum(fix_verdicts.values())
print(f"\n=== Auto-fixes: {total_fixes:,} total ===")
for v, c in fix_verdicts.most_common():
    print(f"  {v}: {c:,}")
print("\nTop field-level fix combos:")
for (v,f), c in sorted(fix_fields.items(), key=lambda x: -x[1])[:15]:
    print(f"  {v:15s} / {f:25s}: {c:,}")

# ── 3. Missing entity additions ───────────────────────────────────────────────
print(f"\n=== Auto-added entities (verdict=add): {len(add_entities)} ===")
add_labels     = collections.Counter(a.get("label","") for a in add_entities)
add_assertions = collections.Counter(a.get("assertion","") for a in add_entities)
add_snomed_ok  = sum(1 for a in add_entities if a.get("snomed_resolved") or a.get("snomed_concept_id"))
print(f"  SNOMED resolved: {add_snomed_ok} / {len(add_entities)}")
print(f"  Labels:     {dict(add_labels.most_common())}")
print(f"  Assertions: {dict(add_assertions.most_common())}")
print("  Sample added entities:")
for a in add_entities[:8]:
    print(f"    [{a.get('assertion','?'):12s}] {a.get('label','?'):20s} | {a.get('text','?')[:50]} | {a.get('rationale','')[:60]}")

# ── 4. Entity removals ────────────────────────────────────────────────────────
print(f"\n=== Auto-removed entities: {len(remove_entities):,} ===")
remove_confs = [r.get("confidence", 0) for r in remove_entities]
if remove_confs:
    print(f"  confidence: min={min(remove_confs):.2f} mean={statistics.mean(remove_confs):.2f} max={max(remove_confs):.2f}")
print("  Sample rationales:")
seen = set()
for r in remove_entities:
    rat = r.get("rationale","")[:80]
    if rat not in seen:
        seen.add(rat)
        print(f"    [{r.get('confidence',0):.2f}] {rat}")
    if len(seen) >= 6:
        break

# ── 5. Field-level fix quality ────────────────────────────────────────────────
assertion_fixes = [fx for r in records for fx in r.get("auto_fixes",[])
                   if fx.get("field") == "assertion" and fx.get("verdict") in ("fixable","needs_review")]
text_fixes      = [fx for r in records for fx in r.get("auto_fixes",[])
                   if fx.get("field") == "text" and fx.get("verdict") in ("fixable","needs_review")]
label_fixes     = [fx for r in records for fx in r.get("auto_fixes",[])
                   if fx.get("field") == "label"]

print(f"\n=== Field fix samples ===")
print(f"Assertion fixes: {len(assertion_fixes):,}")
seen2 = set()
for fx in assertion_fixes[:10]:
    key = (fx.get("current"), fx.get("suggested"))
    if key not in seen2:
        seen2.add(key)
        print(f"  {fx.get('current'):15s} -> {fx.get('suggested'):15s} | conf={fx.get('confidence',0):.2f} | {fx.get('rationale','')[:60]}")

print(f"\nLabel fixes: {len(label_fixes):,}")
lf_counts = collections.Counter((fx.get("current"), fx.get("suggested")) for fx in label_fixes)
for (cur,sug), cnt in lf_counts.most_common(8):
    print(f"  {str(cur):25s} -> {str(sug):25s}: {cnt}")

# ── 6. Proposals analysis ─────────────────────────────────────────────────────
all_proposals = [p for r in records for p in r.get("proposals", [])]
prop_verdicts = collections.Counter(p.get("verdict","") for p in all_proposals)
prop_fields   = collections.Counter((p.get("verdict",""), str(p.get("field",""))) for p in all_proposals)
prop_confs    = [p.get("confidence",0) for p in all_proposals]

print(f"\n=== Proposals (manual review needed): {len(all_proposals):,} ===")
for v, c in prop_verdicts.most_common():
    print(f"  {v}: {c:,}")
print("\nTop (verdict, field):")
for (v,f), c in sorted(prop_fields.items(), key=lambda x: -x[1])[:10]:
    print(f"  {v:15s} / {f:20s}: {c:,}")
if prop_confs:
    print(f"\nProposal confidence: min={min(prop_confs):.2f} mean={statistics.mean(prop_confs):.2f} max={max(prop_confs):.2f}")
    actionable = sum(1 for c in prop_confs if c >= 0.85)
    print(f"High-conf proposals (>=0.85) that could be reviewed quickly: {actionable:,}")

# ── 7. Data quality flags ─────────────────────────────────────────────────────
all_dqf = [d for r in records for d in r.get("data_quality_flags", [])]
dqf_fields = collections.Counter(str(d.get("field","")) for d in all_dqf)
print(f"\n=== Data quality flags (non-actionable, excluded from proposals): {len(all_dqf):,} ===")
for f, c in dqf_fields.most_common():
    print(f"  {f}: {c:,}")

# ── 8. Errors ─────────────────────────────────────────────────────────────────
errors = [r for r in records if r.get("error")]
print(f"\n=== Errors: {len(errors)} ===")
err_msgs = collections.Counter(r.get("error","")[:80] for r in errors)
for msg, cnt in err_msgs.most_common(5):
    print(f"  [{cnt}] {msg}")

# ── 9. Consensus stats ────────────────────────────────────────────────────────
consensus_recs = [r for r in records if r.get("consensus")]
escalated = sum(1 for r in consensus_recs if r.get("consensus",{}).get("escalated"))
print(f"\n=== Consensus (records with consensus info): {len(consensus_recs):,} ===")
print(f"  Escalated to big model: {escalated:,} ({100*escalated/max(len(consensus_recs),1):.1f}%)")
print(f"  Settled by small models: {len(consensus_recs)-escalated:,} ({100*(len(consensus_recs)-escalated)/max(len(consensus_recs),1):.1f}%)")
