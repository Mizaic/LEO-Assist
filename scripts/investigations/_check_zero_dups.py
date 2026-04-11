import requests

r = requests.get(
    "http://localhost:8001/terminology/surface-forms/duplicates", timeout=30
)
data = r.json()
print(f"Remaining duplicates: {len(data)}")
for d in data:
    norm = d.get("normalized", "?")
    count = d.get("rel_count", 0)
    print(f"  {norm} ({count} mappings):")
    for m in d.get("mappings", []):
        cid = m.get("concept_id")
        fsn = m.get("concept_fsn", "")[:50]
        prov = m.get("provenance", "?")
        print(f"    {cid}  {fsn}  prov={prov}")
if not data:
    print("Zero duplicates. Surface form dictionary is clean.")
