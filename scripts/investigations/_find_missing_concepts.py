"""Find correct SNOMED concept IDs for atypical depression and separation anxiety."""

import requests

BASE = "http://localhost:8001/terminology"

for q in [
    "atypical depression",
    "separation anxiety disorder",
    "atypical depressive disorder",
    "anxiety disorder separation",
]:
    r = requests.get(
        f"{BASE}/search",
        params={"q": q, "limit": 5, "semantic_tag": "disorder"},
        timeout=30,
    )
    if r.ok:
        items = r.json()[:5]
        print(f"{q!r}:")
        for item in items:
            cid = item.get("snomed_concept_id") or item.get("id", "?")
            term = (item.get("snomed_term") or item.get("term") or "?")[:70]
            print(f"  {cid} | {term}")
