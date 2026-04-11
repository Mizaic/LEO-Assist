"""Show POSSIBLE_EXISTENCE ConText rules and check for 'likely' gaps."""

import json
from pathlib import Path

p = Path("libs/ner/resources/uk_primary_care_context_rules.json")
data = json.loads(p.read_text(encoding="utf-8"))
rules = data.get("context_rules", [])
print(f"Total rules: {len(rules)}")

possible = [r for r in rules if r.get("category") == "POSSIBLE_EXISTENCE"]
print(f"\nPOSSIBLE_EXISTENCE rules ({len(possible)}):")
for r in possible:
    print(f"  [{r['direction']:10}] scope={r['max_scope']:2}  \"{r['literal']}\"")

# Check for likely/probable
literals = {r["literal"].lower() for r in rules}
gaps = [
    "likely",
    "probably",
    "probable",
    "suspected",
    "suspect",
    "possibly",
    "appears to",
    "seems to",
    "consistent with",
    "may have",
    "might have",
    "possibly",
    "possible that",
]
print("\nMissing speculative markers:")
for g in gaps:
    if g not in literals:
        print(f'  MISSING: "{g}"')
    else:
        print(f'  present: "{g}"')
