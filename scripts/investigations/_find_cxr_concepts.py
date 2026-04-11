"""Find correct SNOMED IDs for CXR finding concepts via terminology API."""

import requests

API = "http://localhost:8001/terminology"
SEARCHES = [
    ("lung mass", ["finding", "morphologic abnormality"]),
    ("pulmonary nodule", ["finding", "disorder"]),
    ("hilar lymphadenopathy", ["disorder", "finding"]),
    ("mediastinal mass", ["finding", "disorder"]),
    ("mediastinal widening", ["finding", "morphologic abnormality"]),
    ("lung consolidation", ["disorder", "finding", "morphologic abnormality"]),
    ("lung opacity", ["finding", "morphologic abnormality"]),
    ("abnormal chest x-ray finding", ["finding"]),
    ("pleural effusion", ["disorder", "finding"]),
    ("atelectasis", ["disorder"]),
]


def search(term: str, prefer_tags: list) -> None:
    r = requests.get(f"{API}/search", params={"q": term, "limit": 6}, timeout=15)
    if r.status_code != 200:
        print(f"  {term!r}: HTTP {r.status_code}")
        return
    hits = r.json() if isinstance(r.json(), list) else r.json().get("results", [])
    print(f"\n  [{term}]")
    for h in hits:
        cid = h.get("snomed_concept_id", "?")
        tag = h.get("semantic_tag", "?")
        fsn = h.get("term", "?")
        preferred = " <-- PREFER" if tag in prefer_tags else ""
        print(f"    {cid:20s} ({tag:30s}) {fsn[:55]}{preferred}")


for term, tags in SEARCHES:
    search(term, tags)
