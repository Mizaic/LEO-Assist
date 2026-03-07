"""Look at missing entity rationales and the actual encounter texts to understand what's being missed."""
import json, sys, collections

trail = sys.argv[1] if len(sys.argv) > 1 else "scripts/agentic_audit_trail_20260306_175817.jsonl"

# Look at all records to find comma-list patterns in entity_verdicts
# and check whether missing_entities match
pass_records_with_one_entity = []
records_with_comma_in_text = []
all_missing_rationales = []

with open(trail) as f:
    for line in f:
        rec = json.loads(line)
        text = rec.get("encounter_text", "") or rec.get("text", "") or ""
        missing = rec.get("missing_entities", [])
        entities = rec.get("entities", [])
        ev = rec.get("entity_verdicts", [])
        verdict = rec.get("record_verdict", "")

        for m in missing:
            all_missing_rationales.append(m.get("rationale", "")[:120])

        # Look for records that passed but likely should have more entities
        if verdict == "pass" and len(entities) == 1 and "," in text:
            pass_records_with_one_entity.append({
                "text": text[:250],
                "entity_label": entities[0].get("label","") if entities else "",
                "entity_text": entities[0].get("text","") if entities else "",
            })

# Show all missing rationales grouped
rat_counts = collections.Counter(all_missing_rationales)
print(f"Total missing_entities entries: {len(all_missing_rationales)}")
print()
print("Top missing entity rationale patterns:")
for rat, cnt in rat_counts.most_common(15):
    print(f"  [{cnt:3d}] {rat}")

print()
print(f"\nPass records with 1 entity and comma in text (likely missed list): {len(pass_records_with_one_entity)}")
for r in pass_records_with_one_entity[:8]:
    print(f"  label={r['entity_label']} text_snippet={r['entity_text']!r}")
    print(f"  encounter: {r['text']}")
    print()
