"""
Analyse surface_form_gaps.json -- group, sort, and report on resolver gaps.
"""
import json
from collections import defaultdict
from pathlib import Path

gap_path = Path(__file__).parent / "encounter_audit" / "surface_form_gaps.json"
gaps = json.loads(gap_path.read_text(encoding="utf-8"))

total = len(gaps)
print(f"Total surface form gaps: {total:,}")
print()

# ---- 1. By gap type --------------------------------------------------------
by_type = defaultdict(int)
for g in gaps:
    by_type[g.get("gap_type", "unknown")] += 1
print("=== By gap type ===")
for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
    pct = 100 * n // total
    print(f"  {t:<15s} {n:5,}  ({pct}%)")
print()

# ---- 2. By target concept (what we are TRYING to resolve to) ---------------
by_concept = defaultdict(lambda: {"not_found": 0, "wrong_rank": 0, "total": 0,
                                   "concept_id": "", "semantic_tag": ""})
for g in gaps:
    name = g.get("expected_name") or "Unknown"
    gt = g.get("gap_type", "unknown")
    by_concept[name]["total"] += 1
    by_concept[name][gt] = by_concept[name].get(gt, 0) + 1
    by_concept[name]["concept_id"] = g.get("expected_concept_id", "")
    by_concept[name]["semantic_tag"] = g.get("semantic_tag", "")

print("=== Top 40 target concepts with gaps ===")
print(f"  {'Total':>5}  {'NotFound':>8}  {'WrongRank':>9}  {'Tag':<20}  Concept Name")
print("  " + "-" * 90)
sorted_concepts = sorted(by_concept.items(), key=lambda x: -x[1]["total"])
for name, d in sorted_concepts[:40]:
    tag = d["semantic_tag"] or "-"
    nf = d.get("not_found", 0)
    wr = d.get("wrong_rank", 0)
    print(f"  {d['total']:>5}  {nf:>8}  {wr:>9}  {tag:<20}  {name}")
print()

# ---- 3. Group evidence phrases by semantic category ------------------------
# Categorise by the expected semantic tag
by_tag = defaultdict(lambda: {"count": 0, "concepts": defaultdict(int)})
for g in gaps:
    tag = g.get("semantic_tag") or "unknown"
    name = g.get("expected_name") or "Unknown"
    by_tag[tag]["count"] += 1
    by_tag[tag]["concepts"][name] += 1

print("=== Gaps by semantic tag ===")
for tag, d in sorted(by_tag.items(), key=lambda x: -x[1]["count"]):
    top3 = sorted(d["concepts"].items(), key=lambda x: -x[1])[:3]
    top3_str = ", ".join(f"{n}({c})" for n, c in top3)
    print(f"  {tag:<30s} {d['count']:5,}  top: {top3_str}")
print()

# ---- 4. Not_found deep dive -- these are pure vocab gaps -------------------
nf_gaps = [g for g in gaps if g.get("gap_type") == "not_found"]
nf_by_evidence = defaultdict(lambda: {"count": 0, "targets": set()})
for g in nf_gaps:
    ev = (g.get("evidence") or "").strip()
    name = g.get("expected_name") or "Unknown"
    nf_by_evidence[ev]["count"] += 1
    nf_by_evidence[ev]["targets"].add(name)

print(f"=== NOT_FOUND gaps ({len(nf_gaps):,} total) -- pure vocab gaps ===")
print(f"  Unique evidence phrases: {len(nf_by_evidence):,}")
print()
print("  Top 40 evidence phrases not in resolver at all:")
print(f"  {'Hits':>4}  Evidence phrase  ->  Target concept(s)")
print("  " + "-" * 80)
for ev, d in sorted(nf_by_evidence.items(), key=lambda x: -x[1]["count"])[:40]:
    targets = " | ".join(sorted(d["targets"]))
    ev_disp = ev[:70]
    print(f"  {d['count']:>4}  [{ev_disp}]")
    print(f"        -> {targets}")
print()

# ---- 5. Wrong_rank deep dive -- resolver returns wrong thing first ----------
wr_gaps = [g for g in gaps if g.get("gap_type") == "wrong_rank"]
print(f"=== WRONG_RANK gaps ({len(wr_gaps):,} total) -- resolver ranking issues ===")

# Group by: what are we getting instead (the wrong top result)
wrong_top = defaultdict(int)
for g in wr_gaps:
    top = g.get("resolver_top_result") or "None"
    wrong_top[top] += 1

print("  What the resolver returns INSTEAD (top 20 wrong answers):")
for name, n in sorted(wrong_top.items(), key=lambda x: -x[1])[:20]:
    print(f"  {n:5,}x  [{name}]")
print()

# ---- 6. Actionable surface forms: not_found, not a header/timestamp line ---
import re
HEADER_PAT = re.compile(
    r"(\d{2}:\d{2}|Surgery:|Entered at:|Added in bulk|^[A-Z]{2,}\s*-)", re.I
)
actionable = [
    g for g in nf_gaps
    if g.get("evidence")
    and not HEADER_PAT.search(g.get("evidence", ""))
    and len(g.get("evidence", "")) < 120
]
actionable_ev = defaultdict(lambda: {"count": 0, "targets": set()})
for g in actionable:
    ev = (g.get("evidence") or "").strip()
    actionable_ev[ev]["count"] += 1
    actionable_ev[ev]["targets"].add(g.get("expected_name") or "")

print(f"=== ACTIONABLE not_found phrases (excl. headers/timestamps): {len(actionable_ev):,} unique ===")
print("  Top 50 to add as surface forms:")
for ev, d in sorted(actionable_ev.items(), key=lambda x: -x[1]["count"])[:50]:
    targets = " | ".join(sorted(d["targets"]))
    print(f"  {d['count']:>4}x  [{ev}]  ->  {targets}")
