"""Deeper audit - investigate score 1.30 anomalies and raw vs valid file differences."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALID_FILE = ROOT / "scripts" / "investigations" / "encounter_audit" / "surface_form_gaps_valid.json"
RAW_FILE = ROOT / "scripts" / "investigations" / "encounter_audit" / "surface_form_gaps.json"

valid = json.loads(VALID_FILE.read_text())
raw = json.loads(RAW_FILE.read_text())

# --- Where do score 1.30 entries come from? Check raw file ---
print("=== Score 1.30 entries (first 5 full text) ===")
anomalous = [item for item in valid if item.get("resolver_top_score", 0) >= 1.0]
print(f"Count with score >= 1.0: {len(anomalous)}")
for item in anomalous[:5]:
    print()
    print(f"  evidence: {item.get('evidence')!r}")
    print(f"  expected: {item.get('expected_name')} ({item.get('expected_snomed')})")
    print(f"  score:    {item.get('resolver_top_score')}")
    print(f"  resolver: {item.get('resolver_top_result')!r}")

# --- Check raw file field structure (first entry) ---
print()
print("=== Raw gaps file first entry fields ===")
if raw:
    print(sorted(raw[0].keys()))
    for k, v in raw[0].items():
        print(f"  {k}: {v!r}")

# --- Do raw entries have resolver_top_concept_id? ---
has_rtci_raw = sum(1 for item in raw if item.get("resolver_top_concept_id"))
print(f"\nRaw file: resolver_top_concept_id present in {has_rtci_raw}/{len(raw)}")

# --- What would actually get created by feed script at threshold 0.75? ---
# Simulating feed logic with CORRECT field (expected_snomed) instead of wrong one
above_thresh = [item for item in valid if item.get("resolver_top_score", 0) >= 0.75]
print(f"\n=== Entries above 0.75 threshold: {len(above_thresh)} ===")

# Of those, how many look like sentences (bad surface forms)?
def is_sentence(text):
    if len(text) > 80:
        return True
    words = text.split()
    if len(words) >= 7:
        return True
    starters = ("patient", "reports", "experiencing", "diagnosed",
                 "ongoing", "history of", "an ", "a ct", "a ultra")
    return any(text.lower().startswith(p) for p in starters)

sentences_above = [item for item in above_thresh if is_sentence(str(item.get("evidence", "")))]
phrases_above = [item for item in above_thresh if not is_sentence(str(item.get("evidence", "")))]
print(f"  Sentences (bad surface forms): {len(sentences_above)}")
print(f"  Short phrases (usable):        {len(phrases_above)}")

print()
print("=== Good short phrases above threshold (first 10) ===")
for item in phrases_above[:10]:
    score = item.get("resolver_top_score", 0)
    evidence = item.get("evidence", "")
    expected = item.get("expected_name", "")
    snomed = item.get("expected_snomed", "")
    top_result = item.get("resolver_top_result", "")
    print(f"  [{score:.2f}] {evidence!r}")
    print(f"         expected: {expected!r}")
    print(f"         resolver: {top_result!r}")
    print(f"         resolver == expected? {expected.split('(')[0].strip().lower() in top_result.lower()}")
    print()
