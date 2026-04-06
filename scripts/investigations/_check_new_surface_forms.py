"""Check top missing terms against terminology server to find new surface form candidates."""
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = "http://localhost:8001"

CANDIDATES = [
    # Common conditions appearing 60-216x as missing
    ("hypothyroidism", "underactive thyroid"),
    ("underactive thyroid", None),
    ("iron deficiency anaemia", None),
    ("iron deficiency anemia", None),
    ("gastro-oesophageal reflux disease", None),
    ("GORD", None),
    ("GERD", None),
    ("acid reflux", None),
    ("heart failure", None),
    ("cardiac failure", None),
    ("congestive heart failure", None),
    ("anaemia", None),
    ("anemia", None),
    ("hypertriglyceridaemia", None),
    ("high triglycerides", None),
    ("hypertriglyceridemia", None),
    ("haemoptysis", None),
    ("coughing blood", None),
    ("atrial fibrillation", None),
    ("AF", None),
    ("paroxysmal AF", None),
    ("persistent AF", None),
    ("benign prostatic hyperplasia", None),
    ("BPH", None),
    ("enlarged prostate", None),
    ("allergic rhinitis", None),
    ("hayfever", None),
    ("hay fever", None),
    ("dry eye syndrome", None),
    ("dry eyes", None),
    ("erectile dysfunction", None),
    ("impotence", None),
    ("elevated blood pressure reading", None),
    ("raised blood pressure", None),
    ("medication review done", None),
    ("medication review", None),
    ("structured medication review", None),
    ("informed consent given", None),
    ("consent obtained", None),
    ("telephone consultation", None),
    ("total cholesterol HDL ratio", None),
    ("cholesterol HDL ratio", None),
    ("non-alcoholic fatty liver disease", None),
    ("NAFLD", None),
    ("fatty liver", None),
    ("sleep apnoea", None),
    ("obstructive sleep apnoea", None),
    ("OSA", None),
    ("peripheral neuropathy", None),
    ("diabetic neuropathy", None),
    ("chronic back pain", None),
    ("lower back pain", None),
    ("peripheral arterial disease", None),
    ("PAD", None),
    ("psoriasis", None),
    ("eczema", None),
    ("atopic dermatitis", None),
    ("basal cell carcinoma", None),
    ("BCC", None),
    ("squamous cell carcinoma", None),
    ("SCC skin", None),
    ("chronic pain", None),
    ("neuropathic pain", None),
    ("macrocytosis", None),
    ("B12 deficiency", None),
    ("vitamin B12 deficiency", None),
    ("vitamin D deficiency", None),
    ("folate deficiency", None),
]


def search_term(term: str) -> dict | None:
    try:
        r = requests.get(
            f"{BASE}/terminology/search",
            params={"q": term, "limit": 1},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        results = body if isinstance(body, list) else body.get("results", [])
        return results[0] if results else None
    except Exception as e:
        return None


def check_existing(term: str) -> bool:
    """Check if a surface form mapping already exists."""
    try:
        r = requests.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [term]},
            timeout=15,
        )
        if r.status_code != 200:
            return False
        body = r.json()
        results = body if isinstance(body, list) else body.get("results", [])
        return len(results) > 0 and results[0] is not None
    except Exception:
        return False


print("Checking top missing terms against terminology server...\n")
print(f"{'TERM':<45} {'CONCEPT ID':<15} {'SNOMED NAME':<50} {'ALREADY MAPPED'}")
print("-" * 140)

found = []
for term, alias in CANDIDATES:
    result = search_term(term)
    already = check_existing(term)
    if result:
        cid = result.get("snomed_concept_id") or result.get("conceptId", "?")
        name = result.get("preferredTerm") or result.get("display", "?")
        flag = "YES" if already else "NEEDS MAPPING"
        print(f"  {term:<43} {str(cid):<15} {name[:48]:<50} {flag}")
        if not already:
            found.append((term, cid, name))
    else:
        print(f"  {term:<43} {'NOT FOUND':<15} {'':50} {'--'}")

print()
print(f"=== {len(found)} terms need new surface form mappings ===")
for term, cid, name in found:
    print(f"  '{term}' -> [{cid}] {name}")
