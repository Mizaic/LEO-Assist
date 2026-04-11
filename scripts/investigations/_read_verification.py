import json, sys

p = "scripts/investigations/abbreviation_snomed_verification.json"
try:
    data = json.load(open(p))
except FileNotFoundError:
    print("File not found - script may not have completed")
    sys.exit(1)
print(f"{len(data)} entries in verification file\n")
print(f"{'Abbrev':<10} {'Concept ID':<18} {'Recommended SNOMED term'}")
print("-" * 90)
for r in data:
    cid = r["recommended_concept_id"] or "NOT FOUND"
    term = (r["recommended_term"] or "")[:60]
    print(f"{r['abbreviation']:<10} {cid:<18} {term}")
