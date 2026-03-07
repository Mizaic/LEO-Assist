"""
Deep-dive into specific quality concerns:
1. Are 'needs_review' items being auto-applied correctly?
2. Are label fix 'suggested' values sane (no REMOVE_ENTITY / N/A garbage)?
3. Which trail files have data_quality_flags / add_entity (did new code actually run)?
4. Consensus escalation rate per trail file.
"""
import json, glob, collections

trail_files = sorted(glob.glob("scripts/agentic_audit_trail_*.jsonl"))

print("=== Per-trail: dqf, add_entity, consensus_escalation ===")
print(f"{'File':<45} {'Records':>8} {'dqf':>8} {'add':>6} {'esc%':>7}")
print("-" * 80)

all_bad_label_suggested = []
all_auto_applied_needs_review = []

for path in trail_files:
    fname = path.split("\\")[-1].split("/")[-1]
    total = dqf = add = esc = consensus_total = 0
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                total += 1
                dqf += len(rec.get("data_quality_flags", []))
                ci = rec.get("consensus", {})
                if ci:
                    consensus_total += 1
                    if ci.get("escalated"):
                        esc += 1
                for fx in rec.get("auto_fixes", []):
                    if fx.get("verdict") == "add":
                        add += 1
                    # Check for garbage label suggested values
                    if fx.get("field") == "label":
                        sug = str(fx.get("suggested", ""))
                        if sug.upper() in ("REMOVE_ENTITY", "REMOVE", "N/A", "NONE", "NULL", "") or sug.startswith("REMOVE"):
                            all_bad_label_suggested.append({
                                "file": fname,
                                "current": fx.get("current"),
                                "suggested": sug,
                                "verdict": fx.get("verdict"),
                                "conf": fx.get("confidence"),
                                "rationale": fx.get("rationale","")[:80],
                            })
                    # needs_review being auto-applied - sample them
                    if fx.get("verdict") == "needs_review" and len(all_auto_applied_needs_review) < 10:
                        all_auto_applied_needs_review.append({
                            "file": fname,
                            "field": fx.get("field"),
                            "current": fx.get("current"),
                            "suggested": fx.get("suggested"),
                            "conf": fx.get("confidence"),
                            "rationale": fx.get("rationale","")[:80],
                        })
            except Exception:
                pass
    esc_pct = f"{100*esc/consensus_total:.0f}%" if consensus_total else "n/a"
    print(f"{fname:<45} {total:>8} {dqf:>8} {add:>6} {esc_pct:>7}")

print()
print(f"=== Bad label 'suggested' values (garbage fixes being applied): {len(all_bad_label_suggested)} ===")
bad_counts = collections.Counter((b["current"], b["suggested"]) for b in all_bad_label_suggested)
for (cur, sug), cnt in bad_counts.most_common(10):
    print(f"  {str(cur):25s} -> {str(sug):25s}: {cnt}")
if all_bad_label_suggested:
    print("  Sample:")
    for b in all_bad_label_suggested[:5]:
        print(f"    [{b['conf']}] {b['current']} -> {b['suggested']} | {b['rationale']}")

print()
print("=== 'needs_review' items being auto-applied (partial-fix support) ===")
print("  (These ARE intentional if field is allowed and confidence >= 0.95)")
for nr in all_auto_applied_needs_review:
    print(f"  field={nr['field']:15s} conf={nr['conf']} | {nr['current']} -> {nr['suggested']} | {nr['rationale']}")
