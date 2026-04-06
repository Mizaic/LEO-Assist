"""Find site-specific ultrasound procedure concepts for NG12 actions."""
import requests

BASE = "http://localhost:8001/terminology"

queries = [
    "abdominal ultrasonography",
    "ultrasound scan abdomen",
    "pelvic ultrasound",
    "renal ultrasound",
    "scrotal ultrasound",
    "breast ultrasound",
    "neck ultrasound",
    "liver ultrasound",
    "diagnostic ultrasonography abdomen",
    "direct access ultrasound",
]

for q in queries:
    r = requests.get(f"{BASE}/search",
                     params={"q": q, "limit": 3, "semantic_tag": "procedure"},
                     timeout=30)
    if r.ok:
        items = r.json()[:2]
        print(q + ":")
        for item in items:
            cid = item.get("snomed_concept_id") or item.get("id", "?")
            term = (item.get("snomed_term") or item.get("term") or "?")[:65]
            print(f"  {cid} | {term}")
