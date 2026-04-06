"""Resolve exact SNOMED preferred terms for 'Seen in fast track' concepts.

Uses the exact preferred terms provided by the user to look up the real
concept IDs from the terminology server.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header
import requests

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

TERMS = [
    "Seen in fast track suspected brain tumour clinic (finding)",
    "Seen in fast track suspected breast cancer clinic (finding)",
    "Seen in fast track suspected childrens tumour clinic (finding)",
    "Seen in fast track suspected colorectal cancer clinic (finding)",
    "Seen in fast track suspected gynaecological cancer clinic (finding)",
    "Seen in fast track suspected haematological malignancy clinic (finding)",
    "Seen in fast track suspected head and neck cancer clinic (finding)",
    "Seen in fast track suspected lung cancer clinic (finding)",
    "Seen in fast track suspected sarcoma clinic (finding)",
    "Seen in fast track suspected skin cancer clinic (finding)",
    "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    "Seen in fast track suspected urological cancer clinic (finding)",
]

print(f"Resolving {len(TERMS)} terms via {BASE}/terminology/resolve ...")
print()

r = SESSION.post(f"{BASE}/terminology/resolve", json={"terms": TERMS}, timeout=30)
results = r.json().get("results") or {}

for term in TERMS:
    hits = results.get(term) or []
    top = hits[0] if hits else {}
    cid = top.get("snomed_concept_id", "NOT FOUND")
    label = top.get("snomed_term", "")
    score = top.get("score", "")
    print(f"  {cid}  {term}")
    if label and label != term:
        print(f"           resolved_term: {label}  score={score}")
