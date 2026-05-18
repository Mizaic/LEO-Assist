"""Check SNOMED search scores for problematic terms to understand why
our custom mappings are being overridden.
"""

import requests

BASE = "http://localhost:8001"

for term in ["NAFLD", "type 2 diabetes"]:
    r = requests.get(
        f"{BASE}/terminology/search", params={"q": term, "limit": 5}, timeout=10
    )
    print(f"--- {term} ---")
    for item in r.json():
        cid = item.get("snomed_concept_id", "?")
        score = item.get("score", 0)
        name = item.get("term", "?")
        print(f"  [{cid}] score={score:.2f}  {name}")
    print()

# Also try with high-confidence upsert
print("Trying confidence=10.0 upsert for NAFLD and type 2 diabetes ...")
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

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

for form, cid in [("NAFLD", "9990010007"), ("type 2 diabetes", "44054006")]:
    body = {
        "form": form,
        "normalized": form.lower().strip(),
        "concept_id": cid,
        "confidence": 10.0,
        "source": "manual",
        "provenance": "manual-fix-high-confidence-2026-04-05",
    }
    r = SESSION.post(
        f"{BASE}/terminology/surface-forms/upsert-mapping", json=body, timeout=30
    )
    print(f"  {form} -> [{cid}]: HTTP {r.status_code}")
