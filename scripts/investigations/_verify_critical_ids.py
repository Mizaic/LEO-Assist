"""Look up SNOMED IDs for batch-3 surface forms (breast, rectal bleeding, wound, other)."""

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
    # Breast cancer pathway
    ("skin tethering breast", "finding"),
    ("referral to breast clinic", "procedure"),
    ("fast track referral suspected breast cancer", "procedure"),
    ("lump in breast", "finding"),
    ("breast lump", "finding"),
    ("invasive ductal carcinoma breast", "disorder"),
    ("oestrogen receptor positive", "finding"),
    ("radiotherapy", "procedure"),
    ("radiotherapy breast", "procedure"),
    ("tamoxifen therapy", "procedure"),
    ("vaginal atrophy", "disorder"),
    ("nipple discharge", "finding"),
    ("breast pain", "finding"),
    ("mammogram", "procedure"),
    ("mammography", "procedure"),
    # Rectal / GI bleeding
    ("rectal bleeding", "finding"),
    ("bright red rectal bleeding", "finding"),
    ("haematochezia", "finding"),
    ("melaena", "finding"),
    # Wound care
    ("exposed tendon", "disorder"),
    ("wound dehiscence", "disorder"),
    ("skin graft", "procedure"),
    ("wound infection", "disorder"),
    # Other gaps
    ("vaginal dryness", "finding"),
    ("genitourinary syndrome of menopause", "disorder"),
    ("urinary frequency", "finding"),
    ("nocturia", "finding"),
    ("urinary urgency", "finding"),
    ("haematuria", "finding"),
    ("frank haematuria", "finding"),
    ("microscopic haematuria", "finding"),
    ("dysphagia", "finding"),
    ("difficulty swallowing", "finding"),
    ("fatigue cancer related", "finding"),
    ("peripheral neuropathy", "disorder"),
    ("chemotherapy induced neuropathy", "disorder"),
    ("lymph node biopsy", "procedure"),
    ("CT scan chest abdomen pelvis", "procedure"),
    ("staging CT scan", "procedure"),
    ("PET scan", "procedure"),
    ("DEXA scan", "procedure"),
    ("bone density scan", "procedure"),
    ("colonoscopy", "procedure"),
    ("flexible sigmoidoscopy", "procedure"),
    ("cystoscopy", "procedure"),
]

for q, tag in QUERIES:
    r = requests.get(
        "http://localhost:8001/terminology/search",
        params={"q": q, "limit": 2},
        headers=HEADERS,
        timeout=30,
    )
    body = r.json()
    results = body if isinstance(body, list) else body.get("results", [])
    top = results[0] if results else None
    if top:
        cid = top.get("snomed_concept_id") or ""
        term = top.get("term") or ""
        stag = top.get("semantic_tag") or ""
        print(f"  {cid:20s}  [{stag:20s}]  {q!r:50s}  ->  {term}")
    else:
        print(f"  {'NOT FOUND':20s}  [{tag:20s}]  {q!r}")
