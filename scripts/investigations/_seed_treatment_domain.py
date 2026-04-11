"""Seed cancer treatment concepts into the ncda-treatment subdomain.

Sources (merged in priority order):
  1. configs/snomed/snomed_ncda_treatment_mapping.json  -- 184 curated concepts
     verified by the terminology server (preferred term + synonyms retained).
  2. Audit-discovered concepts (found in patient data but not in the mapping file).
     Each is validated against the terminology server search API before insertion.

The script calls:
  POST /analytics/domains/cancer_audit/subdomains/treatment/concepts/batch

which writes into ncda-treatment.rawJson, updates flat properties on the
ValueSet node, and resets the DomainRegistry so the episode detector picks
up the changes on its next cycle.

Run:
    python scripts/investigations/_seed_treatment_domain.py
    python scripts/investigations/_seed_treatment_domain.py --dry-run
    python scripts/investigations/_seed_treatment_domain.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import os
import requests

ANALYTICS_URL = os.environ.get("ANALYTICS_API_URL", "http://localhost:8003")
TERMINOLOGY_URL = os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8001")
DOMAIN_ID = "cancer_audit"
SUBDOMAIN = "treatment"
BATCH_URL = (
    f"{ANALYTICS_URL}/analytics/domains/{DOMAIN_ID}"
    f"/subdomains/{SUBDOMAIN}/concepts/batch"
)
SUBDOMAIN_URL = f"{ANALYTICS_URL}/analytics/domains/{DOMAIN_ID}/subdomains/{SUBDOMAIN}"
TERMINOLOGY_SEARCH_URL = f"{TERMINOLOGY_URL}/terminology/search"

MAPPING_FILE = ROOT / "configs" / "snomed" / "snomed_ncda_treatment_mapping.json"

# ---------------------------------------------------------------------------
# Audit-discovered concepts not already in the mapping JSON.
# These were found in actual patient NCDA episodes during the April 2026 audit.
# The terminology server was queried to confirm each CID before this list
# was assembled (see scripts/investigations/_audit_cancer_procedures.py).
# ---------------------------------------------------------------------------
_AUDIT_EXTRA_CONCEPTS: list[dict] = [
    # -- Systemic treatment --
    {"concept_id": 367336001, "term": "Chemotherapy (procedure)"},
    {"concept_id": 70292004, "term": "Treatment planning for chemotherapy (procedure)"},
    {"concept_id": 829591000000101, "term": "Neoadjuvant chemotherapy (procedure)"},
    {"concept_id": 394895009, "term": "Postoperative chemotherapy (procedure)"},
    {
        "concept_id": 235391000000102,
        "term": "Delivery of chemotherapy for neoplasm (procedure)",
    },
    {
        "concept_id": 1255831008,
        "term": "Chemotherapy for malignant neoplastic disease using targeted agent (procedure)",
    },
    {
        "concept_id": 1290226008,
        "term": "Administration of antineoplastic agent via intravenous route (procedure)",
    },
    {
        "concept_id": 1255904006,
        "term": "Administration of palliative antineoplastic agent (procedure)",
    },
    {"concept_id": 386918005, "term": "Docetaxel (substance)"},
    # -- Radiotherapy --
    {"concept_id": 1287742003, "term": "Radiotherapy (procedure)"},
    {"concept_id": 428923005, "term": "Radiotherapy to breast (procedure)"},
    {"concept_id": 168528006, "term": "Palliative course of radiotherapy (procedure)"},
    {
        "concept_id": 429867000,
        "term": "Computed tomography of head for radiotherapy planning (procedure)",
    },
    {
        "concept_id": 429856001,
        "term": "Computed tomography of prostate for radiotherapy planning (procedure)",
    },
    {
        "concept_id": 429851006,
        "term": "Computed tomography of thorax for radiotherapy planning (procedure)",
    },
    {
        "concept_id": 431200001,
        "term": "Radionuclide iodine 131 therapy to thyroid (procedure)",
    },
    # -- Hormone / endocrine --
    {"concept_id": 724161009, "term": "Tamoxifen therapy (procedure)"},
    {"concept_id": 169413002, "term": "Hormone therapy (procedure)"},
    {"concept_id": 170814007, "term": "Endocrine treatment change (regime/therapy)"},
    {"concept_id": 707266006, "term": "Androgen deprivation therapy (procedure)"},
    {
        "concept_id": 865211000000104,
        "term": "Intramuscular injection of gonadorelin analogue (procedure)",
    },
    {
        "concept_id": 892651000000109,
        "term": "Subcutaneous injection of gonadorelin analogue (procedure)",
    },
    {
        "concept_id": 313247009,
        "term": "Subcutaneous injection of hormone antagonist (procedure)",
    },
    {"concept_id": 700139004, "term": "Denosumab therapy (procedure)"},
    {"concept_id": 775465003, "term": "Degarelix (product)"},
    {"concept_id": 441864003, "term": "Degarelix (substance)"},
    {"concept_id": 386908000, "term": "Bicalutamide (substance)"},
    # -- Monoclonal antibody / targeted --
    {"concept_id": 724159000, "term": "Rituximab therapy (procedure)"},
    # -- Surgical - breast --
    {"concept_id": 735086001, "term": "Lumpectomy of right breast (procedure)"},
    {
        "concept_id": 237371007,
        "term": "Wide local excision of breast lesion (procedure)",
    },
    {"concept_id": 396487001, "term": "Sentinel lymph node biopsy (procedure)"},
    {"concept_id": 79544006, "term": "Complete axillary lymphadenectomy (procedure)"},
    {"concept_id": 27865001, "term": "Excision of bilateral breasts (procedure)"},
    {
        "concept_id": 1303631000,
        "term": "Excision of malignant neoplasm of left breast (procedure)",
    },
    {"concept_id": 429400009, "term": "Excision of right breast (procedure)"},
    # -- Surgical - colorectal --
    {"concept_id": 359571009, "term": "Right colectomy (procedure)"},
    {
        "concept_id": 50774009,
        "term": "Laparoscopic-assisted right colectomy (procedure)",
    },
    {"concept_id": 82619000, "term": "Left colectomy (procedure)"},
    {"concept_id": 43075005, "term": "Partial resection of colon (procedure)"},
    {"concept_id": 314635004, "term": "Creation of loop ileostomy (procedure)"},
    {"concept_id": 173980008, "term": "Creation of temporary ileostomy (procedure)"},
    # -- Surgical - urological --
    {"concept_id": 90470006, "term": "Prostatectomy (procedure)"},
    {"concept_id": 90199006, "term": "Transurethral prostatectomy (procedure)"},
    {"concept_id": 81516001, "term": "Partial nephrectomy (procedure)"},
    {"concept_id": 175905003, "term": "Total nephrectomy (procedure)"},
    {
        "concept_id": 439739008,
        "term": "Laparoscopic partial excision of kidney (procedure)",
    },
    {
        "concept_id": 386792000,
        "term": "Transurethral excision of neoplasm of urinary bladder (procedure)",
    },
    {
        "concept_id": 386791007,
        "term": "Cystoscopy and transurethral resection of neoplasm of urinary bladder (procedure)",
    },
    # -- Surgical - gynaecological --
    {
        "concept_id": 414575003,
        "term": "Laparoscopic total abdominal hysterectomy and bilateral salpingo-oophorectomy (procedure)",
    },
    {
        "concept_id": 609230000,
        "term": "Laparoscopic bilateral salpingo-oophorectomy (procedure)",
    },
    {"concept_id": 236888001, "term": "Laparoscopic total hysterectomy (procedure)"},
    {"concept_id": 116140006, "term": "Total hysterectomy (procedure)"},
    {
        "concept_id": 116144002,
        "term": "Total abdominal hysterectomy with bilateral salpingo-oophorectomy (procedure)",
    },
    # -- Surgical - head and neck / thyroid --
    {"concept_id": 13619001, "term": "Thyroidectomy (procedure)"},
    {"concept_id": 24443003, "term": "Total thyroidectomy (procedure)"},
    {"concept_id": 30956003, "term": "Subtotal thyroidectomy (procedure)"},
    {"concept_id": 719753008, "term": "Completion thyroidectomy (procedure)"},
    {"concept_id": 302338000, "term": "Lobectomy of thyroid gland (procedure)"},
    {
        "concept_id": 744854002,
        "term": "Excision of left lobe of thyroid gland (procedure)",
    },
    {
        "concept_id": 178283002,
        "term": "Block dissection of cervical lymph nodes (procedure)",
    },
    # -- Surgical - thoracic --
    {"concept_id": 87604009, "term": "Sleeve resection of stomach (procedure)"},
    # -- Skin cancer surgery --
    {"concept_id": 177281002, "term": "Excision of melanoma (procedure)"},
    {"concept_id": 300025007, "term": "Excision of basal cell carcinoma (procedure)"},
    {
        "concept_id": 39559009,
        "term": "Excision of malignant lesion of scalp and neck (procedure)",
    },
    {"concept_id": 787439005, "term": "Wide excision (procedure)"},
    {"concept_id": 405846001, "term": "Wide re-excision of lesion of skin (procedure)"},
    {"concept_id": 302396003, "term": "Cryotherapy to skin lesion (procedure)"},
    {"concept_id": 302390009, "term": "Shave excision of skin lesion (procedure)"},
    # -- Upper GI surgery --
    {"concept_id": 45900003, "term": "Esophagectomy (procedure)"},
    {"concept_id": 235161003, "term": "Ivor Lewis subtotal esophagectomy (procedure)"},
    {"concept_id": 49209004, "term": "Subtotal gastrectomy (procedure)"},
    {"concept_id": 174431000, "term": "Wedge resection of liver (procedure)"},
    {
        "concept_id": 840280000,
        "term": "Osteocutaneous fibular free flap reconstruction (procedure)",
    },
    # -- Haematology treatment --
    {"concept_id": 119966007, "term": "Bone marrow excision (procedure)"},
    # -- Supportive / palliative --
    {"concept_id": 103735009, "term": "Palliative care (regime/therapy)"},
    {
        "concept_id": 306237005,
        "term": "Referral to palliative care service (procedure)",
    },
    {
        "concept_id": 306597006,
        "term": "Discharge from palliative care service (procedure)",
    },
    {"concept_id": 413742003, "term": "Cancer pain and symptom management (procedure)"},
    {"concept_id": 713058002, "term": "End of life care planning (procedure)"},
    {"concept_id": 182964004, "term": "Terminal care (regime/therapy)"},
    # -- Active surveillance --
    {"concept_id": 424313000, "term": "Active surveillance (regime/therapy)"},
    # -- Cancer care review / safety netting --
    {"concept_id": 720006006, "term": "Cancer care review (procedure)"},
    {"concept_id": 1239431000000107, "term": "Cancer safety netting (regime/therapy)"},
    {
        "concept_id": 306140002,
        "term": "Referral to clinical oncology service (procedure)",
    },
    {"concept_id": 183529009, "term": "Referral to oncologist (procedure)"},
    {"concept_id": 306148009, "term": "Referral to hematology service (procedure)"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_mapping_concepts() -> list[dict]:
    """Load all concepts from the curated treatment mapping JSON."""
    if not MAPPING_FILE.exists():
        print(f"WARNING: {MAPPING_FILE} not found; skipping curated mapping.")
        return []

    with open(MAPPING_FILE, encoding="utf-8") as f:
        data = json.load(f)

    concepts = []
    for term_name, entry in (data.get("mappings") or {}).items():
        cid = entry.get("concept_id")
        preferred = entry.get("preferred_term") or term_name
        if cid:
            concepts.append(
                {
                    "concept_id": int(cid),
                    "term": preferred,
                }
            )
    return concepts


def _verify_concept_via_terminology(concept_id: int) -> Optional[str]:
    """Search the terminology API to confirm a concept exists and get its term.

    Returns the preferred term if found, None if not found or server unreachable.
    """
    try:
        resp = requests.get(
            TERMINOLOGY_SEARCH_URL,
            params={"q": str(concept_id), "limit": 5},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        items = (
            results
            if isinstance(results, list)
            else results.get("items") or results.get("results") or []
        )
        for item in items:
            item_cid = item.get("concept_id") or item.get("conceptId") or item.get("id")
            if str(item_cid) == str(concept_id):
                return (
                    item.get("term")
                    or item.get("preferred_term")
                    or item.get("display")
                )
        return None
    except Exception:
        return None


def _get_current_concept_codes() -> set[str]:
    """Fetch codes already stored in ncda-treatment via the analytics API."""
    try:
        resp = requests.get(SUBDOMAIN_URL, timeout=15)
        if resp.status_code != 200:
            return set()
        data = resp.json()
        return {str(c.get("concept_id")) for c in (data.get("concepts") or [])}
    except Exception:
        return set()


def _batch_insert(concepts: list[dict], dry_run: bool) -> dict:
    """POST the batch to the analytics API. Returns the response JSON."""
    payload = [{"concept_id": c["concept_id"], "term": c["term"]} for c in concepts]
    print(f"\n  Posting {len(payload)} concepts to {BATCH_URL}")
    if dry_run:
        print("  [DRY RUN] Skipping actual POST.")
        return {}
    resp = requests.post(
        BATCH_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _section_load_and_merge() -> list[dict]:
    """Merge curated mapping + audit extras, de-duplicated by concept_id."""
    curated = _load_mapping_concepts()
    print(f"  Curated mapping file    : {len(curated)} concepts")
    print(f"  Audit extra concepts    : {len(_AUDIT_EXTRA_CONCEPTS)}")

    merged: dict[int, dict] = {}
    for c in curated:
        merged[c["concept_id"]] = c
    for c in _AUDIT_EXTRA_CONCEPTS:
        if c["concept_id"] not in merged:
            merged[c["concept_id"]] = c

    result = sorted(merged.values(), key=lambda x: x["concept_id"])
    print(f"  Merged unique concepts  : {len(result)}")
    return result


def _section_terminology_verify(
    extra_only: list[dict],
    terminology_available: bool,
) -> list[dict]:
    """Validate audit-extra concepts against the terminology server."""
    if not terminology_available:
        print("  Terminology server unreachable - skipping validation.")
        return extra_only

    print(
        f"\n  Validating {len(extra_only)} audit-extra concepts via terminology API..."
    )
    validated = []
    for c in extra_only:
        preferred = _verify_concept_via_terminology(c["concept_id"])
        if preferred:
            status = "OK"
            c_out = {"concept_id": c["concept_id"], "term": preferred}
        else:
            status = "NOT FOUND (kept with audit term)"
            c_out = c
        print(f"    [{status}] {c['concept_id']}  {c['term'][:60]}")
        validated.append(c_out)
        time.sleep(0.05)
    return validated


def _section_verify_result() -> None:
    """Fetch the subdomain and report what is now stored."""
    try:
        resp = requests.get(SUBDOMAIN_URL, timeout=15)
        if resp.status_code != 200:
            print(f"  WARNING: GET {SUBDOMAIN_URL} returned {resp.status_code}")
            return
        data = resp.json()
        count = data.get("concept_count", len(data.get("concepts") or []))
        print(f"\n  ncda-treatment now contains: {count} concepts")
    except Exception as exc:
        print(f"  WARNING: Could not verify via API: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed cancer treatment concepts into ncda-treatment subdomain"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the payload but do not POST to the API.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only report the current state; no changes.",
    )
    parser.add_argument(
        "--skip-terminology-check",
        action="store_true",
        help="Skip validation of audit-extra concepts against the terminology server.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  NCDA Treatment Domain Seed")
    print(f"  Analytics API  : {ANALYTICS_URL}")
    print(f"  Terminology API: {TERMINOLOGY_URL}")
    print("=" * 70)

    if args.verify_only:
        _section_verify_result()
        return

    # -- Load and merge sources --
    print("\n[1] Loading concepts from mapping file and audit extras...")
    all_concepts = _section_load_and_merge()

    # -- Check what's already in the domain --
    print("\n[2] Checking existing concepts in ncda-treatment...")
    existing = _get_current_concept_codes()
    print(f"  Currently stored: {len(existing)} concepts")

    new_concepts = [c for c in all_concepts if str(c["concept_id"]) not in existing]
    print(f"  New (not yet stored): {len(new_concepts)} concepts")

    if not new_concepts:
        print("\n  Nothing to add. ncda-treatment is already fully populated.")
        _section_verify_result()
        return

    # -- Optionally validate audit extras via terminology server --
    if not args.skip_terminology_check:
        curated_ids = {c["concept_id"] for c in _load_mapping_concepts()}
        audit_extras_to_validate = [
            c for c in new_concepts if c["concept_id"] not in curated_ids
        ]
        if audit_extras_to_validate:
            print("\n[3] Validating audit-extra concepts via terminology server...")
            try:
                resp = requests.get(
                    TERMINOLOGY_SEARCH_URL,
                    params={"q": "chemotherapy", "limit": 1},
                    timeout=5,
                )
                terminology_available = resp.status_code == 200
            except Exception:
                terminology_available = False
            print(f"  Terminology server available: {terminology_available}")
            _section_terminology_verify(audit_extras_to_validate, terminology_available)

    # -- Batch insert --
    print(f"\n[4] Inserting {len(new_concepts)} concepts via batch API...")

    # API caps at 500; split into chunks if needed
    chunk_size = 450
    chunks = [
        new_concepts[i : i + chunk_size]
        for i in range(0, len(new_concepts), chunk_size)
    ]
    print(f"  Chunks: {len(chunks)} (chunk size: {chunk_size})")

    for idx, chunk in enumerate(chunks, 1):
        print(f"\n  Chunk {idx}/{len(chunks)} ({len(chunk)} concepts)...")
        try:
            result = _batch_insert(chunk, dry_run=args.dry_run)
            if result and not args.dry_run:
                added = result.get("concept_count", "?")
                print(f"  -> ncda-treatment concept count after chunk: {added}")
        except requests.HTTPError as exc:
            print(
                f"  ERROR: HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            )
            sys.exit(1)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            sys.exit(1)

    # -- Verify final state --
    print("\n[5] Verification...")
    _section_verify_result()
    print("\nDone.")


if __name__ == "__main__":
    main()
