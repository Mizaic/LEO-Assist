"""Quick validation script for the exclusion training JSONL."""
import json, pprint
from pathlib import Path

path = Path("exports/ner/training/exclusion_domain_v1.jsonl")
records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]

errors = 0
for r in records:
    text = r["text"]
    for e in r["entities"]:
        actual = text[e["start"]:e["end"]]
        if actual != e["text"]:
            print(f"[{r['document_id']}] {e['entity_id']}: expected {e['text']!r} got {actual!r}")
            errors += 1

print(f"Total records : {len(records)}")
print(f"Offset errors : {errors}")
print()
pprint.pprint(records[0], depth=4)
