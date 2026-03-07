"""Analyse missing-entity proposals to find the comma-list pattern."""
import json, re, sys, collections

trail = sys.argv[1] if len(sys.argv) > 1 else "scripts/agentic_audit_trail_20260306_175817.jsonl"

comma_list_pattern = re.compile(
    r'\b(?:no|not|without|denies?|denied|absence of|no associated|no history of)'
    r'[\w\s]+'
    r'(?:,\s*[\w\s]+){2,}',
    re.IGNORECASE,
)

comma_list_hits = 0
other_missing = 0
label_counts = collections.Counter()
sample_comma = []
sample_other = []

with open(trail) as f:
    for line in f:
        rec = json.loads(line)
        text = rec.get("encounter_text", "") or ""
        for m in rec.get("missing_entities", []):
            rat = m.get("rationale", "")
            label = m.get("label", "?")
            label_counts[label] += 1
            if comma_list_pattern.search(text) and (
                "list" in rat.lower() or "comma" in rat.lower()
                or "also" in rat.lower() or "associated" in rat.lower()
                or "palpitat" in rat.lower() or "nausea" in rat.lower()
            ):
                comma_list_hits += 1
                if len(sample_comma) < 5:
                    sample_comma.append({
                        "text": text[:200],
                        "rationale": rat[:150],
                        "label": label,
                    })
            else:
                other_missing += 1
                if len(sample_other) < 5:
                    sample_other.append({
                        "rationale": rat[:150],
                        "label": label,
                    })

print(f"Total missing entity proposals: {comma_list_hits + other_missing}")
print(f"  Likely comma-list pattern:    {comma_list_hits}")
print(f"  Other missing entities:       {other_missing}")
print()
print("Label distribution:")
for lbl, cnt in label_counts.most_common():
    print(f"  {lbl}: {cnt}")
print()
print("=== Sample comma-list misses ===")
for s in sample_comma:
    print(f"  label={s['label']}")
    print(f"  text:  {s['text']}")
    print(f"  why:   {s['rationale']}")
    print()
print("=== Sample other misses ===")
for s in sample_other:
    print(f"  label={s['label']}  {s['rationale']}")
