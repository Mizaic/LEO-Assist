"""Verify batch 7 concept IDs before writing."""
import sys, requests
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.terminology.client import TerminologyClient

VERIFY = [
    ("paroxysmal atrial fibrillation", "282825002"),
    ("persistent atrial fibrillation", "440028005"),
    ("diabetic neuropathy", "230572002"),
    ("lower back pain", "279039007"),
    ("peripheral vascular disease", "400047006"),
    ("intermittent claudication", "60399004"),
    ("squamous cell carcinoma skin", "402815007"),
    ("vitamin B12 deficiency", "190634004"),
    ("chronic pain", "82423001"),
    ("CPAP", "78275009"),
    ("LUTS", "266569009"),
    ("CCF", "48447003"),
    ("LVF", "84114007"),
    ("SMR", "1239511000000100"),
]

client = TerminologyClient()
BASE = "http://localhost:8001"

print(f"{'SEARCH':<40} {'WANT':<16} {'GOT ID':<16} {'GOT NAME'}")
print("-" * 110)

for term, want_id in VERIFY:
    r = requests.get(f"{BASE}/terminology/resolve-one",
                     params={"term": term}, timeout=15)
    if r.status_code == 200:
        d = r.json()
        got_id = str(d.get("concept_id") or d.get("snomed_concept_id") or "?")
        got_name = d.get("term") or d.get("preferredTerm") or "?"
        match = "OK" if got_id == str(want_id) else "DIFF"
    else:
        results = client.resolve([term])
        hits = results.get(term, [])
        if hits:
            got_id = str(hits[0].concept_id)
            got_name = hits[0].term
            match = "OK" if got_id == str(want_id) else "DIFF"
        else:
            got_id = "NOT FOUND"
            got_name = ""
            match = "MISS"
    print(f"  {match}  {term:<38} {str(want_id):<16} {got_id:<16} {got_name[:50]}")
