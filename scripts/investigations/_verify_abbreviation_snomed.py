"""
Verify correct SNOMED concepts for medical abbreviations before writing
surface forms to the terminology server.

For each abbreviation, we:
  1. Search by the plain-English expansion to find the best candidate concept.
  2. Also try searching by the abbreviation itself to see what currently
     resolves (may be nothing, wrong concept, or already correct).
  3. Print a side-by-side report for human sign-off.

Run:  python scripts/investigations/_verify_abbreviation_snomed.py
"""

from __future__ import annotations

import json
import time
import requests

BASE = "http://localhost:8001"
SEARCH_URL = f"{BASE}/terminology/search"
RESOLVE_URL = f"{BASE}/terminology/resolve"


# ---------------------------------------------------------------------------
# Abbreviations to verify.
# Format: (abbreviation, plain_english_expansion, expected_semantic_tag,
#           note_to_reviewer)
# Tier 1 = cancer-pathway; Tier 2 = high-volume chronic; Tier 3 = symptoms;
# Tier 4 = investigations.
# ---------------------------------------------------------------------------
ABBREVIATIONS = [
    # -- Tier 1: Cancer pathway (safety-critical) --
    (
        "2WW",
        "two week wait cancer referral",
        "procedure",
        "All tumour-site 2WW SNOMED codes",
    ),
    ("FIT", "faecal immunochemical test", "procedure", "Bowel cancer screening FIT"),
    ("FOBT", "faecal occult blood test", "procedure", "Older FOBT term"),
    ("FOB", "faecal occult blood", "procedure", "Short form of FOBT"),
    ("SLL", "small lymphocytic lymphoma", "disorder", "Same entity as CLL variant"),
    ("CLL", "chronic lymphocytic leukaemia", "disorder", "Most common adult leukaemia"),
    ("BCC", "basal cell carcinoma", "disorder", "Skin cancer - very common"),
    ("SCC", "squamous cell carcinoma", "disorder", "Skin/lung/other SCC"),
    ("CA", "malignant neoplasm", "disorder", "'prostate CA', 'CA breast'"),
    ("CA125", "cancer antigen 125 serum", "observable entity", "Ovarian cancer marker"),
    ("ADT", "androgen deprivation therapy", "procedure", "Prostate cancer treatment"),
    (
        "GOJ",
        "gastro-oesophageal junction adenocarcinoma",
        "disorder",
        "GOJ adenocarcinoma",
    ),
    ("PSA", "prostate specific antigen", "observable entity", "PSA level"),
    # -- Tier 2: High-volume chronic conditions --
    ("HTN", "hypertension", "disorder", "74 hits - biggest gap"),
    ("HbA1c", "haemoglobin A1c level", "observable entity", "HbA1c standalone"),
    ("CKD", "chronic kidney disease", "disorder", "30 hits"),
    ("CBG", "capillary blood glucose", "observable entity", "CBG BB'fast"),
    ("HF", "heart failure", "disorder", "Known HF, COPD, HF"),
    ("IHD", "ischaemic heart disease", "disorder", "venlafaxine CI due to IHD"),
    ("IDA", "iron deficiency anaemia", "disorder", "gastroscopy for IDA"),
    ("GORD", "gastro-oesophageal reflux disease", "disorder", "Diagnosis: GORD"),
    ("T2DM", "type 2 diabetes mellitus", "disorder", "T2DM variant spelling"),
    ("IDDM", "insulin dependent diabetes mellitus", "disorder", "IDDM variant"),
    ("BPH", "benign prostatic hyperplasia", "disorder", "BG of IHD, ILD, COPD, BPH"),
    ("ILD", "interstitial lung disease", "disorder", "BG of IHD, ILD, COPD"),
    # -- Tier 3: Symptoms and clinical findings --
    ("SOBOE", "shortness of breath on exertion", "finding", "11 hits - very common"),
    ("SOB", "dyspnoea", "finding", "shortness of breath"),
    ("TATT", "fatigue", "finding", "tired all the time"),
    ("CIBH", "change in bowel habit", "finding", "persistent CIBH"),
    ("CP", "chest pain", "finding", "CP / dizziness"),
    ("PV", "vaginal bleeding", "finding", "PV bleeding"),
    ("NAD", "no abnormality detected", "finding", "Xray NAD, FOBT NAD"),
    ("OOH", "out of hours", "finding", "OOH report"),
    ("TWOC", "trial without catheter", "procedure", "failed TWOC - urinary retention"),
    ("IMB", "intermenstrual bleeding", "finding", "1x episode IMB"),
    ("PR", "per rectum bleeding", "finding", "PR bleeding on wiping"),
    # -- Tier 4: Investigations and procedures --
    ("XR", "plain x-ray", "procedure", "26 hits - f/u XR"),
    ("US", "ultrasonography", "procedure", "US Pelvis"),
    ("ECHO", "echocardiogram", "procedure", "ECHO severe AS"),
    ("GFR", "estimated glomerular filtration rate", "observable entity", "GFR G3b"),
    (
        "eGFR",
        "estimated glomerular filtration rate",
        "observable entity",
        "eGFR in context",
    ),
    ("TSH", "thyroid stimulating hormone level", "observable entity", "Serum TSH"),
    ("HBPM", "home blood pressure monitoring", "observable entity", "Average HBPM"),
    ("MSK", "musculoskeletal", "finding", "MSK back pain"),
    ("LUTS", "lower urinary tract symptoms", "finding", "LUTS / haematuria"),
]


def search(q: str, tag: str, limit: int = 5) -> list[dict]:
    """Search terminology server for best matching concepts."""
    try:
        r = requests.get(
            SEARCH_URL,
            params={"q": q, "limit": limit, "semantic_tag": tag},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return [{"error": str(exc)}]


def resolve(terms: list[str]) -> dict:
    """Call the resolve endpoint with the raw abbreviation."""
    try:
        r = requests.post(
            RESOLVE_URL,
            json={"terms": terms},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def fmt_hit(h: dict) -> str:
    if "error" in h:
        return f"ERROR: {h['error']}"
    cid = h.get("snomed_concept_id", "?")
    term = h.get("term", "?")
    tag = h.get("semantic_tag", "?")
    score = h.get("score", 0)
    return f"  [{cid}] {term} ({tag}) score={score:.2f}"


def main() -> None:
    results = []
    print("=" * 100)
    print("SNOMED concept verification for medical abbreviations")
    print(f"Terminology server: {BASE}")
    print("=" * 100)

    for abbrev, expansion, expected_tag, note in ABBREVIATIONS:
        print(f"\n{'-'*100}")
        print(f"  {abbrev:10s}  | expansion: '{expansion}'  | tag: {expected_tag}")
        print(f"            | note: {note}")

        # 1. Search by expansion
        hits = search(expansion, expected_tag)
        print(f"  Search '{expansion}' [{expected_tag}]:")
        if not hits:
            print("    (no results)")
        for h in hits[:3]:
            print(fmt_hit(h))

        # 2. Resolve raw abbreviation
        res = resolve([abbrev])
        resolved = res.get(abbrev) or res.get(abbrev.lower()) or []
        if isinstance(resolved, list) and resolved:
            top = resolved[0]
            print(
                f"  Resolve '{abbrev}' currently -> [{top.get('concept_id','?')}] "
                f"{top.get('term','?')} (score={top.get('score',0):.2f})"
            )
        else:
            print(f"  Resolve '{abbrev}' currently -> NOT FOUND in resolver")

        # Recommend best concept = top search hit
        rec = None
        if hits and "snomed_concept_id" in hits[0]:
            rec = hits[0]
            results.append(
                {
                    "abbreviation": abbrev,
                    "expansion": expansion,
                    "recommended_concept_id": rec["snomed_concept_id"],
                    "recommended_term": rec["term"],
                    "semantic_tag": rec["semantic_tag"],
                    "score": round(rec["score"], 3),
                    "note": note,
                    "currently_resolves": bool(resolved),
                }
            )
            print(f"  ** RECOMMENDED: [{rec['snomed_concept_id']}] {rec['term']}")
        else:
            results.append(
                {
                    "abbreviation": abbrev,
                    "expansion": expansion,
                    "recommended_concept_id": None,
                    "recommended_term": None,
                    "semantic_tag": expected_tag,
                    "score": 0,
                    "note": note,
                    "currently_resolves": bool(resolved),
                }
            )
            print("  ** NO CANDIDATE FOUND - manual lookup required")

        time.sleep(0.05)  # be gentle on the server

    # Write JSON report for sign-off
    out_path = "scripts/investigations/abbreviation_snomed_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*100}")
    print(f"Written: {out_path}")
    print()
    print("SUMMARY")
    print(
        f"{'Abbrev':<10} {'Concept ID':<16} {'Recommended SNOMED term':<60} {'Currently resolves?'}"
    )
    print("-" * 110)
    for r in results:
        cid = r["recommended_concept_id"] or "NOT FOUND"
        term = (r["recommended_term"] or "")[:58]
        resolves = "YES" if r["currently_resolves"] else "no"
        print(f"{r['abbreviation']:<10} {cid:<16} {term:<60} {resolves}")


if __name__ == "__main__":
    main()
