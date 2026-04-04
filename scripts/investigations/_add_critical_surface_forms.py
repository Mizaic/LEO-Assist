"""Add critical missing surface forms identified from the remediation disputes analysis.

These are high-frequency terms the audit found but the terminology API couldn't resolve.
We verify each against the terminology server before writing.
"""
import sys
import json
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header

TERM_URL = "http://localhost:8001/terminology"
HEADERS = get_service_auth_header()


def search(q: str, semantic_tag: str = "") -> list[dict]:
    params = {"q": q, "limit": 5}
    if semantic_tag:
        params["semantic_tag"] = semantic_tag
    r = requests.get(f"{TERM_URL}/search", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    body = r.json()
    if isinstance(body, list):
        return body
    return body.get("results", [])


def _concept_id(item: dict) -> str:
    """Extract SNOMED concept ID from a search result item (handles both field names)."""
    return str(
        item.get("snomed_concept_id")
        or item.get("conceptId")
        or item.get("concept_id")
        or ""
    )


def _display(item: dict) -> str:
    """Extract preferred display term from a search result item."""
    return (
        item.get("term")
        or item.get("preferredTerm")
        or item.get("display")
        or ""
    )


def upsert(normalized: str, concept_id: str, display: str, confidence: float = 0.95) -> bool:
    body = {
        "normalized": normalized,
        "concept_id": concept_id,
        "display": display,
        "confidence": confidence,
        "source": "manual_audit_gap",
    }
    r = requests.post(
        f"{TERM_URL}/surface-forms/upsert-mapping",
        json=body,
        headers=HEADERS,
        timeout=30,
    )
    return r.status_code in (200, 201)


# -- Terms to add (name, search_query, expected_tag, confidence) -------------
# Verified against SNOMED CT UK Edition via terminology server

CRITICAL_TERMS = [
    # Safety-critical -- missing from resolution
    ("suicidal ideation", "suicidal ideation", "finding", 0.98),
    ("suicidal thoughts", "suicidal ideation", "finding", 0.97),
    ("thoughts of suicide", "suicidal ideation", "finding", 0.97),
    ("thoughts of self-harm suicide", "suicidal ideation", "finding", 0.95),
    ("thoughts of self harm", "suicidal ideation", "finding", 0.95),
    ("child protection plan", "child protection plan", "procedure", 0.98),
    ("on child protection register", "child protection plan", "procedure", 0.95),
    ("child protection case conference", "child protection plan", "procedure", 0.92),

    # Cancer / urgent referrals
    ("secondary malignant neoplasm of bone", "secondary malignant neoplasm of bone", "disorder", 0.97),
    ("bone metastases", "secondary malignant neoplasm of bone", "disorder", 0.95),
    ("bone mets", "secondary malignant neoplasm of bone", "disorder", 0.92),
    ("small lymphocytic lymphoma", "small lymphocytic lymphoma", "disorder", 0.97),
    ("SLL", "small lymphocytic lymphoma", "disorder", 0.85),

    # Mental health
    ("mixed anxiety and depressive disorder", "mixed anxiety and depressive disorder", "disorder", 0.97),
    ("mixed anxiety depression", "mixed anxiety and depressive disorder", "disorder", 0.95),
    ("generalised anxiety disorder", "generalised anxiety disorder", "disorder", 0.97),
    ("generalized anxiety disorder", "generalised anxiety disorder", "disorder", 0.95),
    ("GAD", "generalised anxiety disorder", "disorder", 0.88),

    # Cardiology
    ("first degree atrioventricular block", "first degree atrioventricular block", "disorder", 0.97),
    ("first degree AV block", "first degree atrioventricular block", "disorder", 0.95),
    ("1st degree heart block", "first degree atrioventricular block", "disorder", 0.92),

    # Bowel / GI
    ("change in bowel habit", "change in bowel habit", "finding", 0.97),
    ("altered bowel habit", "change in bowel habit", "finding", 0.95),
    ("change in bowel habits", "change in bowel habit", "finding", 0.95),

    # Menopause
    ("menopausal symptoms", "menopausal symptoms", "finding", 0.97),
    ("perimenopausal symptoms", "menopausal symptoms", "finding", 0.93),
    ("climacteric symptoms", "menopausal symptoms", "finding", 0.90),

    # Facial flushing
    ("facial flushing", "flushing", "finding", 0.92),
    ("hot flushes", "hot flush", "finding", 0.97),
    ("facial flushing finding", "flushing", "finding", 0.90),

    # Lymphoedema
    ("unilateral lower limb lymphoedema", "lymphoedema", "disorder", 0.92),
    ("leg lymphoedema", "lymphoedema", "disorder", 0.90),

    # Electrolytes
    ("hyponatraemia", "hyponatraemia", "disorder", 0.97),
    ("hyponatremia", "hyponatraemia", "disorder", 0.97),
    ("low sodium", "hyponatraemia", "disorder", 0.88),
    ("hypophosphatemia", "hypophosphataemia", "disorder", 0.95),
    ("hypophosphataemia", "hypophosphataemia", "disorder", 0.97),

    # Vascular access
    ("maintenance of peripherally inserted central catheter",
     "maintenance of peripherally inserted central catheter", "procedure", 0.95),
    ("PICC line maintenance", "maintenance of peripherally inserted central catheter", "procedure", 0.90),
    ("PICC line care", "maintenance of peripherally inserted central catheter", "procedure", 0.88),

    # Declined medications
    ("statin declined", "medication declined", "situation", 0.88),
    ("statin refusal", "medication declined", "situation", 0.85),
    ("declined statin", "medication declined", "situation", 0.88),

    # Other high-frequency misses
    ("QRISK2 score", "cardiovascular disease risk score", "observable entity", 0.88),
    ("QRISK2", "cardiovascular disease risk score", "observable entity", 0.85),
    ("QRISK3 score", "cardiovascular disease risk score", "observable entity", 0.88),
    ("urine protein creatinine ratio", "urine protein creatinine ratio", "observable entity", 0.95),
    ("uPCR", "urine protein creatinine ratio", "observable entity", 0.88),
    ("levonorgestrel IUS", "levonorgestrel intrauterine system", "device", 0.92),
    ("mirena coil", "levonorgestrel intrauterine system", "device", 0.92),
    ("LNG-IUS", "levonorgestrel intrauterine system", "device", 0.90),
    ("chronic rhinitis", "chronic rhinitis", "disorder", 0.97),
    ("persistent rhinitis", "chronic rhinitis", "disorder", 0.93),
    ("right knee pain", "knee pain", "finding", 0.92),
    ("left knee pain", "knee pain", "finding", 0.92),
    ("knee pain", "knee pain", "finding", 0.97),
    ("vaginal candidiasis", "vaginal candidiasis", "disorder", 0.97),
    ("vaginal thrush", "vaginal candidiasis", "disorder", 0.95),
    ("vulvovaginal candidiasis", "vaginal candidiasis", "disorder", 0.95),
    ("hypotension", "hypotension", "disorder", 0.97),
    ("low blood pressure", "hypotension", "disorder", 0.93),
    ("chronic diarrhoea", "chronic diarrhoea", "finding", 0.97),
    ("chronic diarrhea", "chronic diarrhoea", "finding", 0.95),
    ("chronic loose stools", "chronic diarrhoea", "finding", 0.90),
    ("referral to urology service", "referral to urology service", "procedure", 0.95),
    ("urology referral", "referral to urology service", "procedure", 0.93),
    ("rheumatoid arthritis", "rheumatoid arthritis", "disorder", 0.98),
    ("RA", "rheumatoid arthritis", "disorder", 0.82),
]


def main() -> None:
    print(f"Verifying and writing {len(CRITICAL_TERMS)} surface form mappings...\n")
    written = 0
    skipped = 0
    failed = 0

    for surface_form, search_query, expected_tag, confidence in CRITICAL_TERMS:
        # Search for the concept
        results = search(search_query, expected_tag)
        if not results:
            # Try without semantic tag filter
            results = search(search_query)

        if not results:
            print(f"  NOT FOUND: {surface_form!r} (search: {search_query!r})")
            skipped += 1
            continue

        top = results[0]
        concept_id = _concept_id(top)
        display = _display(top) or search_query

        if not concept_id:
            print(f"  NO CONCEPT_ID: {surface_form!r}")
            skipped += 1
            continue

        ok = upsert(surface_form.lower().strip(), concept_id, display, confidence)
        if ok:
            print(f"  OK  {surface_form!r} -> {concept_id} | {display}")
            written += 1
        else:
            print(f"  FAIL {surface_form!r}")
            failed += 1

    print(f"\nDone: {written} written, {skipped} not found, {failed} failed")


if __name__ == "__main__":
    main()
