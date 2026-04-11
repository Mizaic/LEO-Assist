"""Audit the surface_form_gaps_valid.json before feeding into Neo4j."""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALID_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "surface_form_gaps_valid.json"
)

data = json.loads(VALID_FILE.read_text())
print(f"Total entries: {len(data)}")

# --- Field inventory ---
all_keys = set()
for item in data:
    all_keys.update(item.keys())
print("\nFields present:", sorted(all_keys))

# --- Field matching vs what feed script expects ---
print("\nField presence audit (vs feed script expectations):")
for field in (
    "evidence",
    "resolver_top_concept_id",
    "expected_concept_id",
    "expected_snomed",
    "resolver_top_result",
    "resolver_top_score",
    "expected_name",
    "encounter_id",
):
    count = sum(1 for item in data if item.get(field))
    print(f"  {field:<30} present in {count:>5}/{len(data)} records")

# --- Score distribution ---
scores = [item.get("resolver_top_score", 0) for item in data]
buckets = Counter()
for s in scores:
    if s == 0.5:
        buckets["0.50 (floor/no match)"] += 1
    elif s < 0.75:
        buckets["0.51-0.74"] += 1
    elif s < 0.85:
        buckets["0.75-0.84"] += 1
    elif s < 0.95:
        buckets["0.85-0.94"] += 1
    else:
        buckets[">=0.95"] += 1

print("\nScore distribution:")
for k, v in sorted(buckets.items()):
    pct = 100 * v / len(data)
    print(f"  {k:<25} {v:>5}  ({pct:.1f}%)")

above_threshold = sum(1 for s in scores if s >= 0.75)
print(f"\n  Above default threshold (0.75): {above_threshold} of {len(data)}")

# --- Gap type breakdown ---
gap_types = Counter(item.get("gap_type") for item in data)
print("\nGap type breakdown:")
for gt, n in gap_types.most_common():
    print(f"  {gt:<20} {n:>5}")


# --- Quality check: full sentences vs short phrases ---
def looks_like_sentence(text):
    words = text.split()
    return len(words) >= 7 or any(
        text.lower().startswith(p)
        for p in (
            "patient",
            "reports",
            "experiencing",
            "diagnosed",
            "ongoing",
            "history of",
        )
    )


sentences = [
    item for item in data if looks_like_sentence(str(item.get("evidence", "")))
]
short_phrases = [
    item for item in data if not looks_like_sentence(str(item.get("evidence", "")))
]
print(f"\nPhrase quality:")
print(f"  Short clinical phrases (good surface forms): {len(short_phrases)}")
print(f"  Full sentences (poor surface forms): {len(sentences)}")

# --- High-confidence examples ---
print("\nHigh confidence examples (score >= 0.85):")
high = sorted(
    [item for item in data if item.get("resolver_top_score", 0) >= 0.85],
    key=lambda x: -x.get("resolver_top_score", 0),
)
for item in high[:8]:
    score = item.get("resolver_top_score", 0)
    evidence = item.get("evidence", "")[:60]
    top = item.get("resolver_top_result", "")[:60]
    expected = item.get("expected_name", "")[:60]
    snomed = item.get("expected_snomed", "")
    print(f"  [{score:.2f}] {evidence!r}")
    print(f"         resolver: {top!r}")
    print(f"         expected: {expected!r} ({snomed})")
    print()

# --- Low-quality / sentence examples ---
print("\nSentence-like entries (first 5):")
for item in sentences[:5]:
    score = item.get("resolver_top_score", 0)
    evidence = item.get("evidence", "")
    print(f"  [{score:.2f}] {evidence!r}")
