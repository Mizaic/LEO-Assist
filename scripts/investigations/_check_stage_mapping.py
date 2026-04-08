"""Check stage_of_diagnosis mapping for specific concept IDs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

stage_path = ROOT / "configs" / "snomed" / "snomed_ncda_stage_of_diagnosis_mapping.json"
with open(stage_path) as f:
    stage = json.load(f)

mappings = stage.get("mappings", {})
print(f"Total stage_of_diagnosis entries: {len(mappings)}")

TARGETS = {"78873005", "10743008"}
print("\nChecking for target concept IDs:")
for label, entry in mappings.items():
    cid = str(entry.get("concept_id", ""))
    if cid in TARGETS:
        term = entry.get("preferred_term", "")
        print(f"  FOUND: {label!r} -> concept_id={cid}, term={term}")

# Also check guideline_synonyms / synonyms entries
for label, entry in mappings.items():
    for syn_entry in entry.get("guideline_synonyms", []):
        if isinstance(syn_entry, dict):
            cid = str(syn_entry.get("concept_id", ""))
            if cid in TARGETS:
                print(f"  FOUND (synonym): {label!r} synonym concept_id={cid}")

print("\nSample entries:")
for label, entry in list(mappings.items())[:8]:
    cid = entry.get("concept_id", "")
    term = entry.get("preferred_term", "")[:55]
    print(f"  {label!r}: cid={cid}, term={term}")
