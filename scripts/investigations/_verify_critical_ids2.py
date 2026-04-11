"""Second-pass lookups for batch-6 terms that returned wrong concepts."""

import sys, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception as e:
    print(f"[WARN] KV: {e}")
from libs.auth.service_auth import get_service_auth_header

HEADERS = get_service_auth_header()

QUERIES = [
    # enlarged lymph node - returned submandibular-specific
    ("enlarged lymph node", "finding"),
    ("lymph node enlargement", "finding"),
    ("palpable lymph node", "finding"),
    # gynaecological surgery - returned referral
    ("gynaecological operation", "procedure"),
    ("pelvic surgery", "procedure"),
    ("laparoscopic surgery pelvis", "procedure"),
    # adjustment disorder - returned generic mental disorder
    ("adjustment disorder", "disorder"),
    ("adjustment reaction", "disorder"),
    ("adjustment disorder anxiety", "disorder"),
    ("reactive depression", "disorder"),
    # fit note - returned self-isolation note
    ("fitness for work statement", "record artifact"),
    ("fit note", "procedure"),
    ("fitness for work certificate", "procedure"),
    # bowel surgery complication - returned laser surgery complication
    ("complication of bowel surgery", "disorder"),
    ("complication of intestinal surgery", "disorder"),
    ("small bowel complication", "disorder"),
    # macroalbuminuria
    ("macroalbuminuria", "finding"),
    ("proteinuria", "finding"),
    ("heavy proteinuria", "finding"),
    ("overt nephropathy", "disorder"),
    # metatarsal tenderness - returned generic tenderness
    ("tenderness of metatarsal", "finding"),
    ("metatarsal pain", "finding"),
    ("metatarsalgia", "disorder"),
    # CKD KDIGO additional
    ("albuminuria", "finding"),
    ("urine albumin creatinine ratio", "observable entity"),
]

for q, tag in QUERIES:
    r = requests.get(
        "http://localhost:8001/terminology/search",
        params={"q": q, "limit": 3},
        headers=HEADERS,
        timeout=30,
    )
    body = r.json()
    results = body if isinstance(body, list) else body.get("results", [])
    print(f"\n  query: {q!r}")
    for top in results[:3]:
        cid = top.get("snomed_concept_id") or ""
        term = top.get("term") or ""
        stag = top.get("semantic_tag") or ""
        print(f"    {cid:22s}  [{stag:20s}]  {term}")
