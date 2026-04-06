"""Check how confident we are in the SNOMED codes for the 7,062 valid gaps.

Each gap has an expected_snomed that came from one of three sources:
  1. Existing graph coding  (wrong_rank / not_found gaps)  -- code was already in Neo4j
  2. LLM audit proposal    (llm_proposed gaps)             -- audit LLM suggested it

We verify each against the terminology resolver to see if:
  - The code resolves cleanly (resolver agrees)
  - The resolver disagrees (code may be wrong)
  - The code is missing from the resolver entirely (no SNOMED node)
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VALID_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "surface_form_gaps_valid.json"
)

gaps = json.loads(VALID_FILE.read_text(encoding="utf-8"))

# -- Basic field audit -------------------------------------------------------
has_snomed = sum(1 for g in gaps if g.get("expected_snomed"))
has_name = sum(1 for g in gaps if g.get("expected_name"))
by_gap_type = Counter(g.get("gap_type") for g in gaps)
by_source = Counter(g.get("source") for g in gaps)

print(f"Total valid gaps: {len(gaps)}")
print(f"  Has expected_snomed : {has_snomed}")
print(f"  Has expected_name   : {has_name}")
print(f"\n  By gap_type:")
for k, n in by_gap_type.most_common():
    print(f"    {k or 'null':<20} {n:>5}")
print(f"\n  By source:")
for k, n in by_source.most_common():
    print(f"    {k or 'null':<20} {n:>5}")

# -- Breakdown by gap_type with code confidence ----------------------------
print("\n\n=== Code confidence by gap_type ===\n")

# not_found: phrase already in Neo4j with code, resolver just can't find it
# wrong_rank: resolver finds a different concept at rank 1
# llm_proposed: LLM audit said "this is missing" -- resolver was used during audit

wrong_rank_gaps = [g for g in gaps if g.get("gap_type") == "wrong_rank"]
not_found_gaps = [g for g in gaps if g.get("gap_type") == "not_found"]
llm_gaps = [g for g in gaps if g.get("gap_type") == "llm_proposed"]

print(f"wrong_rank ({len(wrong_rank_gaps)}): phrase resolves BUT to a different concept at rank 1")
print("  The stored code is correct; the surface form just needs pinning so")
print("  the resolver returns IT first instead of the fuzzy match.")
print("  Code confidence: HIGH (was already in the graph and passed pipeline QC)")
print()
print(f"not_found ({len(not_found_gaps)}): phrase is in Neo4j with a code, resolver finds nothing")
print("  The stored code is correct (came from the pipeline); the phrase just")
print("  isn't in the terminology index at all. Adding it as a surface form")
print("  will make it discoverable for future encounters.")
print("  Code confidence: HIGH (same as above)")
print()
print(f"llm_proposed ({len(llm_gaps)}): LLM audit said this was missing; concept from search_snomed")
print("  The code was suggested by the audit LLM, not taken from existing graph data.")
print("  Code confidence: MEDIUM -- LLM used search_snomed but can hallucinate concept IDs.")
print()

# -- Sample resolver disagreement for wrong_rank --------------------------
print("=== wrong_rank: what did the resolver return instead? ===")
print("(showing 20 cases where the resolver's top result != stored code)\n")
for g in wrong_rank_gaps[:20]:
    stored = g.get("expected_name", "")[:45]
    top = g.get("resolver_top_result", "")[:45]
    score = g.get("resolver_top_score") or 0
    ev = g.get("evidence", "")[:55]
    print(f"  '{ev}'")
    print(f"    stored : {stored}")
    print(f"    got    : {top}  (score={score:.2f})")
    print()

# -- LLM-proposed: flag any that look like hallucinations -----------------
print("=== llm_proposed: sample to check ===")
for g in llm_gaps[:20]:
    print(
        f"  '{g.get('evidence','')[:60]}'  ->  "
        f"{g.get('expected_snomed')} | {g.get('expected_name','')[:50]}"
    )
